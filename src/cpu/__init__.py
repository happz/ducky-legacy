import ctypes
import sys
import threading2
import time

import console
import debugging
import instructions
import registers
import mm
import machine.bus
import profiler

from mm import ADDR_FMT, UINT8_FMT, UINT16_FMT, UINT32_FMT, SEGMENT_SIZE, PAGE_SIZE, u16, i16

from registers import Registers, REGISTER_NAMES
from instructions import Opcodes
from errors import AccessViolationError, InvalidResourceError
from util import debug, info, warn, error, print_table, LRUCache, exception

from ctypes import LittleEndianStructure, c_ubyte, c_ushort
from threading2 import Thread

CPU_SLEEP_QUANTUM = 0.1
CPU_INST_CACHE_SIZE = 256

class InterruptVector(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cs', c_ubyte),
    ('ds', c_ubyte),
    ('ip', c_ushort)
  ]

class InvalidOpcodeError(Exception):
  def __init__(self, opcode, ip = None):
    msg = 'Invalid opcode: opcode=%i, ip=%s' % (opcode, ip) if ip else 'Invalid opcode: opcode=%i' % opcode

    super(InvalidOpcodeError, self).__init__(msg)

    self.opcode = opcode
    self.ip = ip

def do_log_cpu_core_state(core, logger = None):
  logger = logger or core.DEBUG

  for i in range(0, Registers.REGISTER_SPECIAL, 4):
    regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
    s = ['reg%02i=%s' % (reg, UINT16_FMT(core.registers.map[reg].value)) for reg in regs]
    logger(' '.join(s))

  logger('cs=%s    ds=%s' % (core.registers.cs, core.registers.ds))
  logger('fp=%s    sp=%s    ip=%s' % (core.registers.fp, core.registers.sp, core.registers.ip))
  logger('priv=%i, hwint=%i, e=%i, z=%i, o=%i, s=%i' % (core.registers.flags.privileged, core.registers.flags.hwint, core.registers.flags.e, core.registers.flags.z, core.registers.flags.o, core.registers.flags.s))
  logger('thread=%s, keep_running=%s, idle=%s, exit=%i' % (core.thread.name if core.thread else '<unknown>', core.keep_running, core.idle, core.exit_code))

  if hasattr(core, 'math_registers'):
    for index, v in enumerate(core.math_registers.stack):
      logger('MS: %02i: %s', index, UINT32_FMT(v))

  if core.current_instruction:
    inst = instructions.disassemble_instruction(core.current_instruction)
    logger('current=%s' % inst)
  else:
    logger('current=<none>')

  for index, (ip, symbol, offset) in enumerate(core.backtrace()):
    logger('Frame #%i: %s + %s (%s)' % (index, symbol, offset, ip))

def log_cpu_core_state(*args, **kwargs):
  do_log_cpu_core_state(*args, **kwargs)

class StackFrame(object):
  def __init__(self, cs, ds, fp):
    super(StackFrame, self).__init__()

    self.CS = cs
    self.DS = ds
    self.FP = fp

  def __getattribute__(self, name):
    if name == 'address':
      return self.DS * SEGMENT_SIZE * PAGE_SIZE + self.FP

    return super(StackFrame, self).__getattribute__(name)

  def __repr__(self):
    return '<StackFrame: CS=%s DS=%s FP=%s (%s)' % (UINT8_FMT(self.CS), UINT8_FMT(self.DS), UINT16_FMT(self.FP), ADDR_FMT(self.address))

class InstructionCache(LRUCache):
  def __init__(self, core, size, *args, **kwargs):
    super(InstructionCache, self).__init__(size, *args, **kwargs)

    self.core = core

  def get_object(self, addr):
    return instructions.decode_instruction(self.core.memory.read_u32(addr))

class DataCache(LRUCache):
  def __init__(self, core, size, *args, **kwargs):
    super(DataCache, self).__init__(size, *args, **kwargs)

    self.core = core

  def make_space(self):
    addr, value = self.popitem(last = False)
    dirty, value = value

    self.core.DEBUG('data_cache.make_space: addr=%s, value=%s', ADDR_FMT(addr), UINT16_FMT(value))

    if dirty:
      self.core.memory.write_u16(addr, value)
    self.prunes += 1

  def get_object(self, addr):
    self.core.DEBUG('data_cache.get_object: addr=%s', ADDR_FMT(addr))

    return [False, self.core.memory.read_u16(addr)]

  def read_u16(self, addr):
    self.core.DEBUG('data_cache.read_u16: addr=%s', ADDR_FMT(addr))

    return self[addr][1]

  def write_u16(self, addr, value):
    self.core.DEBUG('data_cache.write_u16: addr=%s, value=%s', ADDR_FMT(addr), UINT16_FMT(value))

    if addr not in self:
      self.__missing__(addr)

    self[addr] = [True, value]

  def remove_page_references(self, page, writeback = True):
    self.core.DEBUG('data_cache.remove_page_references: page=%s', page.index)

    addresses = [i for i in range(page.base_address, page.base_address + PAGE_SIZE, 2)]

    for addr in self.keys():
      if addr not in addresses:
        continue

      dirty, value = self[addr]

      if dirty and writeback:
        self.core.memory.write_u16(addr, value)
        self.core.DEBUG('data_cache.remove_page_references: %s written back', ADDR_FMT(addr))

      self.core.DEBUG('data_cache.remove_page_references: %s removed', ADDR_FMT(addr))

      del self[addr]

  def flush(self):
    self.core.DEBUG('data_cache.flush')

    for addr in self.keys():
      dirty, value = self[addr]

      if not dirty:
        continue

      self.core.memory.write_u16(addr, value)
      self[addr][0] = False
      self.core.DEBUG('data_cache.flush: %s written back', ADDR_FMT(addr))

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#%u:#%u: ' % (cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.message_bus = self.cpu.machine.message_bus

    self.suspend_lock = threading2.Lock()
    self.suspend_events = []
    self.current_suspend_event = None

    self.registers = registers.RegisterSet()

    self.current_instruction = None

    self.keep_running = True
    self.thread = None
    self.idle = False

    self.machine_profiler = profiler.STORE.get_machine_profiler()
    self.core_profiler = profiler.STORE.get_cpu_profiler(self)

    self.exit_code = 0

    self.frames = []

    self.debug = debugging.DebuggingSet(self)

    self.opcode_map = {}
    for opcode in Opcodes:
      self.opcode_map[opcode.value] = getattr(self, 'inst_%s' % opcode.name)

    self.instruction_cache = InstructionCache(self, CPU_INST_CACHE_SIZE)
    self.data_cache = DataCache(self, CPU_INST_CACHE_SIZE * 4)

    if self.cpu.machine.config.getbool('cpu', 'math-coprocessor', False):
      import cpu.math_coprocessor

      self.math_coprocessor = cpu.math_coprocessor.MathCoprocessor(self)

  def LOG(self, logger, *args):
    args = ('%s ' + args[0],) + (self.cpuid_prefix,) + args[1:]
    logger(*args)

  def DEBUG(self, *args):
    self.LOG(debug, *args)

  def INFO(self, *args):
    self.LOG(info, *args)

  def WARN(self, *args):
    self.LOG(warn, *args)

  def ERROR(self, *args):
    self.LOG(error, *args)

  def __repr__(self):
    return '#%i:#%i' % (self.cpu.id, self.id)

  def save_state(self, state):
    self.DEBUG('core.save_state')

    from core import CPUCoreState

    core_state = CPUCoreState()

    core_state.cpuid = self.cpu.id
    core_state.coreid = self.id

    for reg in REGISTER_NAMES:
      if reg == 'flags':
        core_state.flags = self.registers.flags.to_uint16()

      else:
        setattr(core_state, reg, self.registers.map[reg].value)

    core_state.exit_code = self.exit_code
    core_state.idle = 1 if self.idle else 0
    core_state.keep_running = 1 if self.keep_running else 0

    state.core_states.append(core_state)

  def load_state(self, core_state):
    for reg in REGISTER_NAMES:
      if reg == 'flags':
        self.registers.flags.from_uint16(core_state.flags)

      else:
        self.registers.map[reg].value = getattr(core_state, reg)

    self.exit_code = core_state.exit_code
    self.idle = True if core_state.idle else False
    self.keep_running = True if core_state.keep_running else False

  def EXCEPTION(self, exc):
    exception(exc, logger = self.ERROR)

    do_log_cpu_core_state(self, logger = self.ERROR)

  def die(self, exc):
    self.exit_code = 1

    self.data_cache.flush()

    self.EXCEPTION(exc)

    self.keep_running = False

    self.wake_up()

  def FLAGS(self):
    return self.registers.flags

  def REG(self, reg):
    return self.registers.map[reg]

  def MEM_IN8(self, addr):
    return self.memory.read_u8(addr)

  def MEM_IN16(self, addr):
    return self.data_cache.read_u16(addr)

  def MEM_IN32(self, addr):
    return self.memory.read_u32(addr)

  def MEM_OUT8(self, addr, value):
    self.memory.write_u8(addr, value)

  def MEM_OUT16(self, addr, value):
    self.data_cache.write_u16(addr, value)

  def MEM_OUT32(self, addr, value):
    self.memory.write_u32(addr, value)

  def IP(self):
    return self.registers.ip

  def SP(self):
    return self.registers.sp

  def FP(self):
    return self.registers.fp

  def CS(self):
    return self.registers.cs

  def DS(self):
    return self.registers.ds

  def CS_ADDR(self, address):
    return (self.registers.cs.value & 0xFF) * SEGMENT_SIZE * PAGE_SIZE + address

  def DS_ADDR(self, address):
    return (self.registers.ds.value & 0xFF) * SEGMENT_SIZE * PAGE_SIZE + address

  def fetch_instruction(self):
    ip = self.registers.ip

    self.DEBUG('fetch_instruction: cs=%s, ip=%s', self.registers.cs, ip)

    inst = self.instruction_cache[self.CS_ADDR(ip.value)]
    ip.value += 4

    return inst

  def reset(self, new_ip = 0):
    for reg in registers.RESETABLE_REGISTERS:
      self.REG(reg).value = 0

    self.registers.flags.privileged = 0
    self.registers.flags.hwint = 1
    self.registers.flags.e = 0
    self.registers.flags.z = 0
    self.registers.flags.o = 0
    self.registers.flags.s = 0

    self.registers.ip.value = new_ip

    self.instruction_cache.clear()

  def __symbol_for_ip(self):
    ip = self.registers.ip

    symbol, offset = self.cpu.machine.get_symbol_by_addr(self.registers.cs.value, ip.value)

    if not symbol:
      self.WARN('symbol_for_ip: Unknown jump target: %s', ip)
      return

    self.DEBUG('symbol_for_ip: %s%s (%s)', symbol, ' + %s' % offset if offset != 0 else '', ip.value)

  def backtrace(self):
    bt = []

    for frame_index, frame in enumerate(self.frames):
      ip = self.memory.read_u16(frame.address + 2, privileged = True)
      symbol, offset = self.cpu.machine.get_symbol_by_addr(frame.CS, ip)

      bt.append((ip, symbol, offset))

    ip = self.registers.ip.value - 4
    symbol, offset = self.cpu.machine.get_symbol_by_addr(self.registers.cs.value, ip)
    bt.append((ip, symbol, offset))

    return bt

  def __raw_push(self, val):
    self.registers.sp.value -= 2
    self.data_cache.write_u16(self.DS_ADDR(self.registers.sp.value), val)

  def __raw_pop(self):
    ret = self.data_cache.read_u16(self.DS_ADDR(self.registers.sp.value))
    self.registers.sp.value += 2
    return ret

  def __push(self, *regs):
    for reg_id in regs:
      reg = self.registers.map[reg_id]

      self.DEBUG('__push: %s (%s) at %s', reg_id, reg, UINT16_FMT(self.registers.sp.value - 2))
      value = self.registers.flags.to_uint16() if reg_id == Registers.FLAGS else self.registers.map[reg_id].value
      self.__raw_push(value)

  def __pop(self, *regs):
    for reg_id in regs:
      if reg_id == Registers.FLAGS:
        self.registers.flags.from_uint16(self.__raw_pop())
      else:
        self.registers.map[reg_id].value = self.__raw_pop()

      self.DEBUG('__pop: %s (%s) from %s', reg_id, self.registers.map[reg_id], UINT16_FMT(self.registers.sp.value - 2))

  def __create_frame(self):
    self.DEBUG('__create_frame')

    self.__push(Registers.IP, Registers.FP)

    self.registers.fp.value = self.registers.sp.value

    self.frames.append(StackFrame(self.registers.cs.value, self.registers.ds.value, self.registers.fp.value))

  def __destroy_frame(self):
    self.DEBUG('__destroy_frame')

    if self.frames[-1].FP != self.registers.sp.value:
      raise CPUException('Leaving frame with wrong SP: IP=%s, saved SP=%s, current SP=%s' % (ADDR_FMT(self.registers.ip.value), ADDR_FMT(self.frames[-1].FP), ADDR_FMT(self.registers.sp.value)))

    self.__pop(Registers.FP, Registers.IP)

    self.frames.pop()

    self.__symbol_for_ip()

  def __enter_interrupt(self, table_address, index):
    self.DEBUG('__enter_interrupt: table=%s, index=%i', table_address, index)

    iv = self.memory.load_interrupt_vector(table_address, index)

    stack_pg, sp = self.memory.alloc_stack(segment = iv.ds)

    old_SP = self.registers.sp.value
    old_DS = self.registers.ds.value

    self.registers.ds.value = iv.ds
    self.registers.sp.value = sp

    self.__raw_push(old_DS)
    self.__raw_push(old_SP)
    self.__push(Registers.CS, Registers.FLAGS)
    self.__push(*[i for i in range(0, Registers.REGISTER_SPECIAL)])
    self.__create_frame()

    self.privileged = 1

    self.registers.cs.value = iv.cs
    self.registers.ip.value = iv.ip

  def __exit_interrupt(self):
    self.DEBUG('__exit_interrupt')

    self.__destroy_frame()
    self.__pop(*[i for i in reversed(range(0, Registers.REGISTER_SPECIAL))])
    self.__pop(Registers.FLAGS, Registers.CS)

    stack_page = self.memory.get_page(mm.addr_to_page(self.DS_ADDR(self.registers.sp.value)))

    old_SP = self.__raw_pop()
    old_DS = self.__raw_pop()

    self.registers.ds.value = old_DS
    self.registers.sp.value = old_SP

    self.data_cache.remove_page_references(stack_page, writeback = False)
    self.memory.free_page(stack_page)

  def __do_int(self, index):
    self.DEBUG('__do_int: %s', index)

    if index in self.cpu.machine.virtual_interrupts:
      self.DEBUG('__do_int: calling virtual interrupt')

      self.cpu.machine.virtual_interrupts[index].run(self)

      self.DEBUG('__do_int: virtual interrupt finished')

    else:
      self.__enter_interrupt(self.memory.int_table_address, index)

      self.DEBUG('__do_int: CPU state prepared to handle interrupt')

  def __do_irq(self, index):
    self.DEBUG('__do_irq: %s', index)

    self.__enter_interrupt(self.memory.irq_table_address, index)
    self.registers.flags.hwint = 0
    self.idle = False

    self.DEBUG('__do_irq: CPU state prepared to handle IRQ')
    log_cpu_core_state(self)

  # Do it this way to avoid pylint' confusion
  def __get_privileged(self):
    return self.registers.flags.privileged

  def __set_privileged(self, value):
    self.registers.flags.privileged = value

  privileged = property(__get_privileged, __set_privileged)

  def __check_protected_ins(self):
    if not self.privileged:
      raise AccessViolationError('Instruction not allowed in unprivileged mode: opcode=%i' % self.current_instruction.opcode)

  def check_protected_reg(self, *regs):
    for reg in regs:
      if reg in registers.PROTECTED_REGISTERS and not self.privileged:
        raise AccessViolationError('Access not allowed in unprivileged mode: opcode=%i reg=%i' % (self.current_instruction.opcode, reg))

  def __check_protected_port(self, port):
    if port not in self.cpu.machine.ports:
      raise InvalidResourceError('Unhandled port: port=%u' % port)

    if self.cpu.machine.ports[port].is_protected and not self.privileged:
      raise AccessViolationError('Access to port not allowed in unprivileged mode: opcode=%i, port=%u' % (self.current_instruction.opcode, port))

  def __update_arith_flags(self, *regs):
    F = self.registers.flags

    F.z = 0
    F.o = 0
    F.s = 0

    for reg in regs:
      if reg.value == 0:
        F.z = 1

      x = ctypes.cast((u16 * 1)(reg), ctypes.POINTER(i16)).contents.value
      if x < 0:
        F.s = 1

  def RI_VAL(self, inst):
    return self.registers.map[inst.ireg].value if inst.is_reg == 1 else inst.immediate

  def JUMP(self, inst):
    src_addr = self.registers.ip.value - 4

    if inst.is_reg == 1:
      self.registers.ip.value = self.registers.map[inst.ireg].value
    else:
      self.registers.ip.value += inst.immediate

    dst_addr = self.registers.ip.value
    self.core_profiler.trigger_jump(src_addr, dst_addr)

    self.__symbol_for_ip()

  def CMP(self, x, y, signed = True):
    F = self.registers.flags

    F.e = 0
    F.z = 0
    F.o = 0
    F.s = 0

    if signed:
      x = ctypes.cast((u16 * 1)(x), ctypes.POINTER(i16)).contents.value
      y = ctypes.cast((u16 * 1)(y), ctypes.POINTER(i16)).contents.value

    if x == y:
      F.e = 1

      if x == 0:
        F.z = 1

    elif x < y:
      F.s = 1

    elif x > y:
      F.s = 0

  def OFFSET_ADDR(self, inst):
    self.DEBUG('offset addr: ireg=%s, imm=%s', inst.ireg, inst.immediate)

    addr = self.registers.map[inst.ireg].value
    if inst.immediate != 0:
      addr += inst.immediate

    self.DEBUG('offset addr: addr=%s', addr)
    return self.DS_ADDR(addr)

  #
  # Opcode handlers
  #
  def inst_NOP(self, inst):
    pass

  def inst_LW(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value = self.data_cache.read_u16(self.OFFSET_ADDR(inst))
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_LB(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value = self.memory.read_u8(self.OFFSET_ADDR(inst))
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_LI(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value = inst.immediate
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_STW(self, inst):
    self.data_cache.write_u16(self.OFFSET_ADDR(inst), self.registers.map[inst.reg].value)

  def inst_STB(self, inst):
    self.memory.write_u8(self.OFFSET_ADDR(inst), self.registers.map[inst.reg].value & 0xFF)

  def inst_MOV(self, inst):
    self.registers.map[inst.reg1].value = self.registers.map[inst.reg2].value

  def inst_SWP(self, inst):
    v = self.registers.map[inst.reg1].value
    self.registers.map[inst.reg1].value = self.registers.map[inst.reg2].value
    self.registers.map[inst.reg2].value = v

  def inst_CAS(self, inst):
    self.registers.flags.e = 0

    v = self.memory.cas_16(self.DS_ADDR(self.registers.map[inst.r_addr]), self.registers.map[inst.r_test], self.registers.map[inst.r_rep])
    if v is True:
      self.registers.flags.e = 1
    else:
      self.registers.map[inst.r_test].value = v.value

  def inst_INT(self, inst):
    self.__do_int(self.RI_VAL(inst))

  def inst_RETINT(self, inst):
    self.__check_protected_ins()

    self.__exit_interrupt()

  def inst_CALL(self, inst):
    self.__create_frame()

    self.JUMP(inst)

  def inst_RET(self, inst):
    self.__destroy_frame()

  def inst_CLI(self, inst):
    self.__check_protected_ins()

    self.registers.flags.hwint = 0

  def inst_STI(self, inst):
    self.__check_protected_ins()

    self.registers.flags.hwint = 1

  def inst_HLT(self, inst):
    self.__check_protected_ins()

    self.exit_code = self.RI_VAL(inst)

    self.keep_running = False

  def inst_RST(self, inst):
    self.__check_protected_ins()

    self.reset()

  def inst_IDLE(self, inst):
    self.idle = True

  def inst_PUSH(self, inst):
    self.__raw_push(self.RI_VAL(inst))

  def inst_POP(self, inst):
    self.check_protected_reg(inst.reg)

    self.__pop(inst.reg)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_INC(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value += 1
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_DEC(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value -= 1
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_ADD(self, inst):
    self.check_protected_reg(inst.reg)
    v = self.registers.map[inst.reg].value + self.RI_VAL(inst)
    self.registers.map[inst.reg].value += self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])
    if v > 0xFFFF:
      self.registers.flags.o = 1

  def inst_SUB(self, inst):
    self.check_protected_reg(inst.reg)
    v = self.RI_VAL(inst) > self.registers.map[inst.reg].value
    self.registers.map[inst.reg].value -= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

    if v:
      self.registers.flags.s = 1

  def inst_AND(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value &= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_OR(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value |= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_XOR(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value ^= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_NOT(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value = ~self.registers.map[inst.reg].value
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_SHIFTL(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value <<= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_SHIFTR(self, inst):
    self.check_protected_reg(inst.reg)
    self.registers.map[inst.reg].value >>= self.RI_VAL(inst)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_IN(self, inst):
    port = self.RI_VAL(inst)

    self.__check_protected_port(port)
    self.check_protected_reg(inst.reg)

    self.registers.map[inst.reg].value = self.cpu.machine.ports[port].read_u16(port)

  def inst_INB(self, inst):
    port = self.RI_VAL(inst)

    self.__check_protected_port(port)
    self.check_protected_reg(inst.reg)

    self.registers.map[inst.reg].value = self.cpu.machine.ports[port].read_u8(port)
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_OUT(self, inst):
    port = self.RI_VAL(inst)

    self.__check_protected_port(port)

    self.cpu.machine.ports[port].write_u16(port, self.registers.map[inst.reg].value)

  def inst_OUTB(self, inst):
    port = self.RI_VAL(inst)

    self.__check_protected_port(port)

    self.cpu.machine.ports[port].write_u8(port, self.registers.map[inst.reg].value & 0xFF)

  def inst_CMP(self, inst):
    self.CMP(self.registers.map[inst.reg].value, self.RI_VAL(inst))

  def inst_CMPU(self, inst):
    self.CMP(self.registers.map[inst.reg].value, self.RI_VAL(inst), signed = False)

  def inst_J(self, inst):
    self.JUMP(inst)

  def inst_BE(self, inst):
    if self.registers.flags.e == 1:
      self.JUMP(inst)

  def inst_BNE(self, inst):
    if self.registers.flags.e == 0:
      self.JUMP(inst)

  def inst_BZ(self, inst):
    if self.registers.flags.z == 1:
      self.JUMP(inst)

  def inst_BNZ(self, inst):
    if self.registers.flags.z == 0:
      self.JUMP(inst)

  def inst_BS(self, inst):
    if self.registers.flags.s == 1:
      self.JUMP(inst)

  def inst_BNS(self, inst):
    if self.registers.flags.s == 0:
      self.JUMP(inst)

  def inst_BG(self, inst):
    if self.registers.flags.s == 0 and self.registers.flags.e == 0:
      self.JUMP(inst)

  def inst_BL(self, inst):
    if self.registers.flags.s == 1 and self.registers.flags.e == 0:
      self.JUMP(inst)

  def inst_BGE(self, inst):
    if self.registers.flags.s == 0 or self.registers.flags.e == 1:
      self.JUMP(inst)

  def inst_BLE(self, inst):
    if self.registers.flags.s == 1 or self.registers.flags.e == 1:
      self.JUMP(inst)

  def inst_MUL(self, inst):
    self.check_protected_reg(inst.reg)
    r = self.registers.map[inst.reg]
    x = ctypes.cast((u16 * 1)(r), ctypes.POINTER(i16)).contents.value
    y = ctypes.cast((u16 * 1)(self.RI_VAL(inst)), ctypes.POINTER(i16)).contents.value
    r.value = x * y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_DIV(self, inst):
    self.check_protected_reg(inst.reg)
    r = self.registers.map[inst.reg]
    x = ctypes.cast((u16 * 1)(r), ctypes.POINTER(i16)).contents.value
    y = ctypes.cast((u16 * 1)(self.RI_VAL(inst)), ctypes.POINTER(i16)).contents.value
    r.value = x / y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_MOD(self, inst):
    self.check_protected_reg(inst.reg)
    r = self.registers.map[inst.reg]
    x = ctypes.cast((u16 * 1)(r), ctypes.POINTER(i16)).contents.value
    y = ctypes.cast((u16 * 1)(self.RI_VAL(inst)), ctypes.POINTER(i16)).contents.value
    r.value = x % y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def step(self):
    # pylint: disable-msg=R0912,R0914,R0915
    # "Too many branches"
    # "Too many local variables"
    # "Too many statements"

    saved_IP = self.registers.ip.value

    self.DEBUG('----- * ----- * ----- * ----- * ----- * ----- * ----- * -----')

    # Read next instruction
    self.DEBUG('"FETCH" phase')

    self.current_instruction = self.fetch_instruction()
    opcode = self.current_instruction.opcode

    self.DEBUG('"EXECUTE" phase: %s %s', UINT16_FMT(saved_IP), instructions.disassemble_instruction(self.current_instruction))
    log_cpu_core_state(self)

    if opcode not in self.opcode_map:
      raise InvalidOpcodeError(opcode, ip = saved_IP)

    self.opcode_map[opcode](self.current_instruction)

    self.DEBUG('"SYNC" phase:')
    log_cpu_core_state(self)

  def is_alive(self):
    return self.thread and self.thread.is_alive()

  def is_suspended(self):
    self.DEBUG('is_suspended')

    with self.suspend_lock:
      return self.current_suspend_event is not None

  def wake_up(self):
    self.DEBUG('wake_up')

    with self.suspend_lock:
      if not self.current_suspend_event:
        return

      self.current_suspend_event.set()
      self.current_suspend_event = None

  def suspend_on(self, event):
    self.DEBUG('asked to suspend')
    event.wait()
    self.DEBUG('unsuspended')

  def plan_suspend(self, event):
    self.DEBUG('plan suspend')

    with self.suspend_lock:
      self.suspend_events.append(event)

    self.DEBUG('suspend planned, wait for it')

  def honor_suspend(self):
    with self.suspend_lock:
      if not self.suspend_events:
        return False

      if self.current_suspend_event:
        raise CPUException('existing suspend event: %s' % self.current_suspend_event)

      self.current_suspend_event = self.suspend_events.pop(0)

    self.suspend_on(self.current_suspend_event)

    with self.suspend_lock:
      self.current_suspend_event = None
      return True

  def check_for_events(self):
    self.DEBUG('check_for_events')

    msg = None

    if self.idle:
      self.DEBUG('idle => wait for new messages')
      msg = self.message_bus.receive(self)

    elif self.registers.flags.hwint == 1:
      self.DEBUG('running => check for new message')
      msg = self.message_bus.receive(self, sleep = False)

    self.DEBUG('msg=%s', msg)

    if msg:
      if isinstance(msg, machine.bus.HandleIRQ):
        self.DEBUG('IRQ encountered: %s', msg.irq_source.irq)

        msg.irq_source.clear()
        msg.delivered()

        try:
          self.__do_irq(msg.irq_source.irq)

        except (CPUException, ZeroDivisionError) as e:
          e.exc_stack = sys.exc_info()
          self.die(e)
          return False

      elif isinstance(msg, machine.bus.HaltCore):
        self.keep_running = False

        self.INFO('asked to halt')
        log_cpu_core_state(self)

        msg.delivered()

        return False

      elif isinstance(msg, machine.bus.SuspendCore):
        msg.delivered()
        self.plan_suspend(msg.wake_up)

    self.debug.check()

    if self.honor_suspend():
      self.DEBUG('woken up from suspend state, let check bus for new messages')
      return self.check_for_events()

    return True

  def loop(self):
    self.machine_profiler.enable()

    self.message_bus.register()

    self.INFO('booted')
    log_cpu_core_state(self)

    while self.keep_running:
      if not self.check_for_events():
        break

      if not self.keep_running:
        break

      try:
        self.step()

      except (CPUException, ZeroDivisionError) as e:
        e.exc_stack = sys.exc_info()
        self.die(e)
        break

    self.data_cache.flush()

    self.INFO('halted')
    log_cpu_core_state(self)

    self.machine_profiler.disable()

  def run(self):
    self.thread = Thread(target = self.loop, name = 'Core #%i:#%i' % (self.cpu.id, self.id), priority = 1.0)
    self.thread.start()

  def boot(self, init_state):
    self.DEBUG('boot')

    self.reset()

    cs, ds, sp, ip, privileged = init_state

    self.registers.cs.value = cs
    self.registers.ds.value = ds
    self.registers.ip.value = ip
    self.registers.sp.value = sp
    self.registers.flags.privileged = 1 if privileged else 0

    log_cpu_core_state(self)

class CPU(object):
  def __init__(self, machine, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#%i:' % cpuid

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()
    self.cores = [CPUCore(i, self, self.memory) for i in range(0, cores)]

    self.thread = None

    self.profiler = profiler.STORE.get_machine_profiler()

  def __LOG(self, logger, *args):
    args = ('%s ' + args[0],) + (self.cpuid_prefix,) + args[1:]
    logger(*args)

  def DEBUG(self, *args):
    self.__LOG(debug, *args)

  def INFO(self, *args):
    self.__LOG(info, *args)

  def WARN(self, *args):
    self.__WARN(warn, *args)

  def living_cores(self):
    return filter(lambda x: x.thread and x.thread.is_alive(), self.cores)

  def running_cores(self):
    return filter(lambda x: not x.is_suspended(), self.cores)

  def loop(self):
    self.profiler.enable()

    self.INFO('booted')

    while True:
      time.sleep(CPU_SLEEP_QUANTUM * 10)

      if len(self.living_cores()) == 0:
        break

    self.INFO('halted')

    self.profiler.disable()

  def run(self):
    for core in self.cores:
      core.run()

    self.thread = Thread(target = self.loop, name = 'CPU #%i' % self.id, priority = 0.0)
    self.thread.start()

  def boot(self, init_states):
    for core in self.cores:
      if init_states:
        core.boot(init_states.pop(0))

def cmd_set_core(console, cmd):
  """
  Set core address of default core used by control commands
  """

  console.default_core = console.machine.core(cmd[1])

def cmd_cont(console, cmd):
  """
  Continue execution until next breakpoint is reached
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  core.wake_up()

def cmd_step(console, cmd):
  """
  Step one instruction forward
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  if not core.is_suspended():
    return

  try:
    core.step()
    core.check_for_events()

    log_cpu_core_state(core, logger = core.INFO)

  except CPUException, e:
    core.die(e)

def cmd_next(console, cmd):
  """
  Proceed to the next instruction in the same stack frame.
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  if not core.is_suspended():
    return

  def __ip_addr(offset = 0):
    return core.CS_ADDR(core.registers.ip.value + offset)

  try:
    inst = instructions.decode_instruction(core.memory.read_u32(__ip_addr()))

    if inst.opcode == Opcodes.CALL:
      from debugging import add_breakpoint

      add_breakpoint(core, core.registers.ip.value + 4, ephemeral = True)

      core.wake_up()

    else:
      core.step()
      core.check_for_events()

      log_cpu_core_state(core, logger = core.INFO)

  except CPUException, e:
    core.die(e)

def cmd_core_state(console, cmd):
  """
  Print core state
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  log_cpu_core_state(core, logger = core.INFO)

def cmd_bt(console, cmd):
  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  table = [
    ['Index', 'symbol', 'offset', 'ip']
  ]

  for index, (ip, symbol, offset) in enumerate(core.backtrace()):
    table.append([index, symbol, UINT16_FMT(offset), ADDR_FMT(ip)])

  print_table(table)

console.Console.register_command('sc', cmd_set_core)
console.Console.register_command('cont', cmd_cont)
console.Console.register_command('step', cmd_step)
console.Console.register_command('next', cmd_next)
console.Console.register_command('st', cmd_core_state)
console.Console.register_command('bt', cmd_bt)
