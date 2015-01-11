import collections
import Queue
import sys
import time

import assemble
import debugging
import instructions
import registers
import mm
import machine.bus

from mm import UInt8, UInt16, UInt24
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT
from mm import segment_addr_to_addr

from registers import Registers, REGISTER_NAMES
from instructions import Opcodes
from errors import CPUException, AccessViolationError, InvalidResourceError
from util import debug, info, warn, error, print_table

from ctypes import LittleEndianStructure, Union, c_ubyte, c_ushort, c_uint
from threading2 import Thread

CPU_SLEEP_QUANTUM = 0.1
CPU_INST_CACHE_SIZE = 64

class InterruptVector(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cs', c_ubyte),
    ('ds', c_ubyte),
    ('ip', c_ushort)
  ]

def log_cpu_core_state(core, logger = None):
  logger = logger or core.DEBUG

  for i in range(0, Registers.REGISTER_SPECIAL, 4):
    regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
    s = ['reg%02i=%s' % (reg, core.REG(reg)) for reg in regs]
    logger(' '.join(s))

  logger('cs=%s    ds=%s' % (core.CS(), core.DS()))
  logger('fp=%s    sp=%s    ip=%s' % (core.FP(), core.SP(), core.IP()))
  logger('priv=%i, hwint=%i, e=%i, z=%i, o=%i' % (core.FLAGS().privileged, core.FLAGS().hwint, core.FLAGS().e, core.FLAGS().z, core.FLAGS().o))
  logger('thread=%s, keep_running=%s, idle=%s, exit=%i' % (core.thread.name if core.thread else '<unknown>', core.keep_running, core.idle, core.exit_code))

  if core.current_instruction:
    inst = instructions.disassemble_instruction(core.current_instruction)
    logger('current=%s' % inst)
  else:
    logger('current=<none>')

  for index, (ip, symbol, offset) in enumerate(core.backtrace()):
    logger('Frame #%i: %s + %s (%s)' % (index, symbol, offset, ip))

class StackFrame(object):
  def __init__(self, cs, ds, fp):
    super(StackFrame, self).__init__()

    self.CS = UInt8(cs.u16)
    self.DS = UInt8(ds.u16)
    self.FP = UInt16(fp.u16)

  def __getattribute__(self, name):
    if name == 'address':
      return segment_addr_to_addr(self.DS.u8, self.FP.u16)

    return super(StackFrame, self).__getattribute__(name)

  def __repr__(self):
    return '<StackFrame: CS=%s DS=%s FP=%s (%s)' % (UINT8_FMT(self.CS), UINT8_FMT(self.DS), UINT16_FMT(self.FP), ADDR_FMT(self.address))

class AFLAGS_CTX(object):
  def __init__(self, core, reg):
    super(AFLAGS_CTX, self).__init__()

    self.core = core
    self.reg = reg

  def __enter__(self):
    self.core.FLAGS().z = 0
    self.core.FLAGS().o = 0
    self.core.FLAGS().s = 0

  def __exit__(self, *args, **kwargs):
    self.core.DEBUG('actx_exit: reg=%s' % self.reg)

    if self.reg.u16 == 0:
      self.core.FLAGS().z = 1

    return False

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#%u:#%u: ' % (cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.message_bus = self.cpu.machine.message_bus
    self.suspend_events = []
    self.current_suspend_event = None

    self.registers = registers.RegisterSet()

    self.current_instruction = None

    self.keep_running = True
    self.thread = None
    self.idle = False

    self.exit_code = 0

    self.frames = []

    self.debug = debugging.DebuggingSet(self)

    self.opcode_map = {}
    for opcode in Opcodes:
      self.opcode_map[opcode.value] = getattr(self, 'inst_%s' % opcode.name)

    self.instruction_cache = collections.OrderedDict()

  def __LOG(self, logger, *args):
    args = ('%s ' + args[0],) + (self.cpuid_prefix,) + args[1:]
    logger(*args)

  def DEBUG(self, *args):
    self.__LOG(debug, *args)

  def INFO(self, *args):
    self.__LOG(info, *args)

  def WARN(self, *args):
    self.__LOG(warn, *args)

  def ERROR(self, *args):
    self.__LOG(error, *args)

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
        core_state.flags.u16 = self.registers.flags.u16

      else:
        setattr(core_state, reg, self.registers[reg].u16)

    core_state.exit_code = self.exit_code
    core_state.idle = 1 if self.idle else 0
    core_state.keep_running = 1 if self.keep_running else 0

    state.core_states.append(core_state)

  def load_state(self, core_state):
    for reg in REGISTER_NAMES:
      if reg == 'flags':
        self.registers.flags.u16 = core_state.flags.u16

      else:
        self.registers[reg].u16 = getattr(core_state, reg)

    self.exit_code = core_state.exit_code
    self.idle = True if core_state.idle else False
    self.keep_running = True if core_state.keep_running else False

  def die(self, exc):
    self.exit_code = 1

    self.ERROR(str(exc))
    log_cpu_core_state(self)
    self.keep_running = False

    if self.current_suspend_event:
      self.current_suspend_event.set()

  def FLAGS(self):
    return self.registers.flags.flags

  def REG(self, reg):
    return self.registers[reg]

  def MEM_IN8(self, addr):
    return self.memory.read_u8(addr)

  def MEM_IN16(self, addr):
    return self.memory.read_u16(addr)

  def MEM_IN32(self, addr):
    return self.memory.read_u32(addr)

  def MEM_OUT8(self, addr, value):
    self.memory.write_u8(addr, value)

  def MEM_OUT16(self, addr, value):
    self.memory.write_u16(addr, value)

  def MEM_OUT32(self, addr, value):
    self.memory.write_u16(addr, value)

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
    return segment_addr_to_addr(self.CS().u16 & 0xFF, address)

  def DS_ADDR(self, address):
    return segment_addr_to_addr(self.DS().u16 & 0xFF, address)

  def fetch_instruction(self):
    ip = self.IP()
    addr = self.CS_ADDR(ip.u16)

    self.DEBUG('fetch_instruction: cs=%s, ip=%s, addr=%s', self.CS(), ip, addr)

    C = self.instruction_cache

    if addr not in C:
      self.DEBUG('fetch_instruction: inst cache miss')

      if len(C) == CPU_INST_CACHE_SIZE:
        self.DEBUG('fetch_instruction: inst cache prune')
        C.popitem(last = False)

      ret = self.MEM_IN32(addr)
      C[addr] = inst = instructions.decode_instruction(ret)

    else:
      self.DEBUG('fetch_instruction: inst cache hit')
      inst = C[addr]

    self.IP().u16 += 4

    return inst

  def reset(self, new_ip = 0):
    for reg in registers.RESETABLE_REGISTERS:
      self.REG(reg).u16 = 0

    self.FLAGS().privileged = 0
    self.FLAGS().hwint = 1
    self.FLAGS().e = 0
    self.FLAGS().z = 0
    self.FLAGS().o = 0
    self.FLAGS().s = 0

    self.IP().u16 = new_ip

  def __symbol_for_ip(self):
    symbol, offset = self.cpu.machine.get_symbol_by_addr(UInt8(self.CS().u16), self.IP().u16)

    if not symbol:
      self.WARN('symbol_for_ip: Unknown jump target: %s', self.IP())
      return

    self.DEBUG('symbol_for_ip: %s%s (%s)', symbol, ' + %s' % offset.u16 if offset.u16 != 0 else '', self.IP().u16)

  def backtrace(self):
    bt = []

    for frame_index, frame in enumerate(self.frames):
      ip = self.memory.read_u16(frame.address + 2, privileged = True).u16
      symbol, offset = self.cpu.machine.get_symbol_by_addr(frame.CS, ip)

      bt.append((ip, symbol, offset))

    ip = self.IP().u16 - 4
    symbol, offset = self.cpu.machine.get_symbol_by_addr(UInt8(self.CS().u16), ip)
    bt.append((ip, symbol, offset))

    return bt

  def __raw_push(self, val):
    self.SP().u16 -= 2
    sp = UInt24(self.DS_ADDR(self.SP().u16))
    self.MEM_OUT16(sp.u24, val.u16)

  def __raw_pop(self):
    sp = UInt24(self.DS_ADDR(self.SP().u16))
    ret = self.MEM_IN16(sp.u24).u16
    self.SP().u16 += 2
    return UInt16(ret)

  def __push(self, *regs):
    for reg_id in regs:
      reg = self.REG(reg_id)

      self.DEBUG('__push: %s (%s) at %s', reg_id, reg, UInt16(self.SP().u16 - 2))
      self.__raw_push(self.REG(reg_id))

  def __pop(self, *regs):
    for reg_id in regs:
      reg = self.REG(reg_id)

      reg.u16 = self.__raw_pop().u16
      self.DEBUG('__pop: %s (%s) from %s', reg_id, reg, UInt16(self.SP().u16 - 2))

  def __create_frame(self):
    self.__push(Registers.IP, Registers.FP)

    self.FP().u16 = self.SP().u16

    self.frames.append(StackFrame(self.CS(), self.DS(), self.FP()))

  def __destroy_frame(self):
    if self.frames[-1].FP.u16 != self.SP().u16:
      raise CPUException('Leaving frame with wrong SP: IP=%s, saved SP=%s, current SP=%s' % (ADDR_FMT(self.IP().u16), ADDR_FMT(self.frames[-1].FP.u16), ADDR_FMT(self.SP().u16)))

    self.__pop(Registers.FP, Registers.IP)

    self.frames.pop()

    self.__symbol_for_ip()

  def __enter_interrupt(self, table_address, index):
    self.DEBUG('__enter_interrupt: table=%s, index=%i', table_address, index)

    iv = self.memory.load_interrupt_vector(table_address, index)

    stack_page = self.memory.get_page(self.memory.alloc_page(UInt8(iv.ds)))
    stack_page.read = True
    stack_page.write = True

    old_SP = UInt16(self.SP().u16)
    old_DS = UInt16(self.DS().u16)

    self.DS().u16 = iv.ds
    self.SP().u16 = UInt16(stack_page.segment_address + mm.PAGE_SIZE).u16

    self.__raw_push(old_DS)
    self.__raw_push(old_SP)
    self.__push(Registers.CS, Registers.FLAGS)
    self.__push(*[i for i in range(0, Registers.REGISTER_SPECIAL)])
    self.__create_frame()

    self.privileged = 1

    self.CS().u16 = iv.cs
    self.IP().u16 = iv.ip

  def __exit_interrupt(self):
    self.DEBUG('__exit_interrupt')

    self.__destroy_frame()
    self.__pop(*[i for i in reversed(range(0, Registers.REGISTER_SPECIAL))])
    self.__pop(Registers.FLAGS, Registers.CS)

    stack_page = self.memory.get_page(mm.addr_to_page(self.DS_ADDR(self.SP().u16)))

    old_SP = self.__raw_pop()
    old_DS = self.__raw_pop()

    self.DS().u16 = old_DS.u16
    self.SP().u16 = old_SP.u16

    self.memory.free_page(stack_page)

  def __do_int(self, index):
    self.DEBUG('__do_int: %s', index)

    self.__enter_interrupt(UInt24(self.memory.int_table_address), index)

    self.DEBUG('__do_int: CPU state prepared to handle interrupt')

  def __do_irq(self, index):
    self.DEBUG('__do_irq: %s', index)

    self.__enter_interrupt(UInt24(self.memory.irq_table_address), index)
    self.FLAGS().hwint = 0
    self.idle = False

    self.DEBUG('__do_irq: CPU state prepared to handle IRQ')
    log_cpu_core_state(self)

  # Do it this way to avoid pylint' confusion
  def __get_privileged(self):
    return self.FLAGS().privileged

  def __set_privileged(self, value):
    self.FLAGS().privileged = value

  privileged = property(__get_privileged, __set_privileged)

  def __check_protected_ins(self):
    if not self.privileged:
      raise AccessViolationError('Instruction not allowed in unprivileged mode: opcode=%i' % self.current_instruction.opcode)

  def __check_protected_reg(self, reg):
    if reg in registers.PROTECTED_REGISTERS and not self.privileged:
      raise AccessViolationError('Access not allowed in unprivileged mode: opcode=%i reg=%i' % (self.current_instruction.opcode, reg))

  def __check_protected_port(self, port):
    if port.u16 not in self.cpu.machine.ports:
      raise InvalidResourceError('Unhandled port: port=%u' % port.u16)

    if self.cpu.machine.ports[port.u16].is_protected and not self.privileged:
      raise AccessViolationError('Access to port not allowed in unprivileged mode: opcode=%i, port=%u' % (self.current_instruction.opcode, opcode, port))

  def RI_VAL(self, inst):
    return self.REG(inst.ireg).u16 if inst.is_reg == 1 else inst.immediate

  def JUMP(self, inst):
    if inst.is_reg == 1:
      self.IP().u16 = self.REG(inst.ireg).u16
    else:
      self.IP().u16 += inst.immediate

    self.__symbol_for_ip()

  def CMP(self, x, y):
    self.FLAGS().e = 0
    self.FLAGS().ge = 0
    self.FLAGS().le = 0
    self.FLAGS().s = 0
    self.FLAGS().z = 0

    if   x == y:
      self.FLAGS().e = 1

      if x == 0:
        self.FLAGS().z = 1

    elif x  < y:
      self.FLAGS().s = 1

    elif x > y:
      self.FLAGS().s = 0

  def OFFSET_ADDR(self, inst):
    self.DEBUG('offset addr: ireg=%s, imm=%s', inst.ireg, inst.immediate)

    addr = self.REG(inst.ireg).u16
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
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 = self.MEM_IN16(self.OFFSET_ADDR(inst)).u16

  def inst_LB(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 = self.MEM_IN8(self.OFFSET_ADDR(inst)).u8

  def inst_LI(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 = inst.immediate

  def inst_STW(self, inst):
    self.MEM_OUT16(self.OFFSET_ADDR(inst), self.REG(inst.reg).u16)

  def inst_STB(self, inst):
    self.MEM_OUT8(self.OFFSET_ADDR(inst), self.REG(inst.reg).u16 & 0xFF)

  def inst_MOV(self, inst):
    self.REG(inst.reg1).u16 = self.REG(inst.reg2).u16

  def inst_SWP(self, inst):
    v = UInt16(self.REG(inst.reg1).u16)
    self.REG(inst.reg1).u16 = self.REG(inst.reg2).u16
    self.REG(inst.reg2).u16 = v.u16

  def inst_CAS(self, inst):
    self.FLAGS().e = 0

    v = self.memory.cas_16(self.DS_ADDR(self.REG(inst.r_addr)), self.REG(inst.r_test), self.REG(inst.r_rep))
    if v == True:
      self.FLAGS().e = 1
    else:
      self.REG(inst.r_test).u16 = v.u16

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

    self.FLAGS().hwint = 0

  def inst_STI(self, inst):
    self.__check_protected_ins()

    self.FLAGS().hwint = 1

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
    self.__raw_push(UInt16(self.RI_VAL(inst)))

  def inst_POP(self, inst):
    self.__check_protected_reg(inst.reg)

    self.__pop(inst.reg)

  def inst_INC(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 += 1

  def inst_DEC(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 -= 1

  def inst_ADD(self, inst):
    self. __check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 += self.RI_VAL(inst)

  def inst_SUB(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 -= self.RI_VAL(inst)

  def inst_AND(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 &= self.RI_VAL(inst)

  def inst_OR(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 |= self.RI_VAL(inst)

  def inst_XOR(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 ^= self.RI_VAL(inst)

  def inst_NOT(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 = ~self.REG(inst.reg).u16

  def inst_SHIFTL(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 <<= self.RI_VAL(inst)

  def inst_SHIFTR(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 >>= self.RI_VAL(inst)

  def inst_IN(self, inst):
    port = UInt16(self.RI_VAL(inst))

    self.__check_protected_port(port)
    self.__check_protected_reg(inst.reg)

    self.REG(inst.reg).u16 = self.cpu.machine.ports[port.u16].read_u16(port).u16

  def inst_INB(self, inst):
    port = UInt16(self.RI_VAL(inst))

    self.__check_protected_port(port)
    self.__check_protected_reg(inst.reg)

    self.REG(inst.reg).u16 = UInt16(self.cpu.machine.ports[port.u16].read_u8(port).u8).u16

  def inst_OUT(self, inst):
    port = UInt16(self.RI_VAL(inst))

    self.__check_protected_port(port)

    self.cpu.machine.ports[port.u16].write_u16(port, self.REG(inst.reg))

  def inst_OUTB(self, inst):
    port = UInt16(self.RI_VAL(inst))

    self.__check_protected_port(port)

    self.cpu.machine.ports[port.u16].write_u8(port, UInt8(self.REG(inst.reg).u16 & 0xFF))

  def inst_CMP(self, inst):
    self.CMP(self.REG(inst.reg).u16, self.RI_VAL(inst))

  def inst_J(self, inst):
    self.JUMP(inst)

  def inst_BE(self, inst):
    if self.FLAGS().e == 1:
      self.JUMP(inst)

  def inst_BNE(self, inst):
    if self.FLAGS().e == 0:
      self.JUMP(inst)

  def inst_BZ(self, inst):
    if self.FLAGS().z == 1:
      self.JUMP(inst)

  def inst_BNZ(self, inst):
    if self.FLAGS().z == 0:
      self.JUMP(inst)

  def inst_BS(self, inst):
    if self.FLAGS().s == 1:
      self.JUMP(inst)

  def inst_BNS(self, inst):
    if self.FLAGS().s == 0:
      self.JUMP(inst)

  def inst_BG(self, inst):
    if self.FLAGS().s == 0 and self.FLAGS().e == 0:
      self.JUMP(inst)

  def inst_BL(self, inst):
    if self.FLAGS().s == 1 and self.FLAGS().e == 0:
      self.JUMP(inst)

  def inst_BGE(self, inst):
    if self.FLAGS().s == 0 or self.FLAGS().e == 1:
      self.JUMP(inst)

  def inst_BLE(self, inst):
    if self.FLAGS().s == 1 or self.FLAGS().e == 1:
      self.JUMP(inst)

  def inst_MUL(self, inst):
    self. __check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 *= self.RI_VAL(inst)

  def inst_DIV(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 /= self.RI_VAL(inst)

  def inst_MOD(self, inst):
    self.__check_protected_reg(inst.reg)

    with AFLAGS_CTX(self, self.REG(inst.reg)):
      self.REG(inst.reg).u16 %= self.RI_VAL(inst)

  def step(self):
    # pylint: disable-msg=R0912,R0914,R0915
    # "Too many branches"
    # "Too many local variables"
    # "Too many statements"

    saved_IP = UInt16(self.IP().u16)

    self.DEBUG('----- * ----- * ----- * ----- * ----- * ----- * ----- * -----')

    # Read next instruction
    self.DEBUG('"FETCH" phase')

    self.current_instruction = self.fetch_instruction()
    opcode = self.current_instruction.opcode

    self.DEBUG('"EXECUTE" phase: %s %s', saved_IP, instructions.disassemble_instruction(self.current_instruction))
    log_cpu_core_state(self)

    if opcode not in self.opcode_map:
      raise CPUException('Unknown opcode: %i' % opcode)

    self.opcode_map[opcode](self.current_instruction)

    self.DEBUG('"SYNC" phase:')
    log_cpu_core_state(self)

  def wake_up(self):
    self.DEBUG('wake_up')

    if self.current_suspend_event:
      self.current_suspend_event.set()
      self.current_suspend_event = None

  def suspend_on(self, event):
    self.DEBUG('asked to suspend')
    event.wait()
    self.DEBUG('unsuspended')

  def plan_suspend(self, event):
    self.DEBUG('plan suspend')
    self.suspend_events.append(event)
    self.DEBUG('suspend planned, wait for it')

  def check_for_events(self):
    self.DEBUG('check_for_events')

    msg = None

    if self.idle:
      self.DEBUG('idle => wait for new messages')
      msg = self.message_bus.receive(self)

    elif self.registers.flags.flags.hwint == 1:
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

        except CPUException, e:
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

    if self.suspend_events:
      self.current_suspend_event = self.suspend_events.pop(0)
      self.suspend_on(self.current_suspend_event)
      self.current_suspend_event = None

      self.DEBUG('woken up from suspend state, let check bus for new messages')

      return self.check_for_events()

    return True

  def loop(self):
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

      except CPUException, e:
        self.die(e)
        break

    self.INFO('halted')
    log_cpu_core_state(self)

  def run(self):
    self.thread = Thread(target = self.loop, name = 'Core #%i:#%i' % (self.cpu.id, self.id), priority = 1.0)
    self.thread.start()

  def boot(self, init_state):
    self.DEBUG('boot')

    self.reset()

    cs, ds, sp, ip, privileged = init_state

    self.registers.cs.u16 = cs.u8
    self.registers.ds.u16 = ds.u8
    self.registers.ip.u16 = ip.u16
    self.registers.sp.u16 = sp.u16
    self.FLAGS().privileged = 1 if privileged else 0

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
    return [core for core in self.cores if core.thread and core.thread.is_alive()]

  def loop(self):
    self.INFO('booted')

    while True:
      time.sleep(CPU_SLEEP_QUANTUM * 10)

      if len(self.living_cores()) == 0:
        break

    self.INFO('halted')

  def run(self):
    for core in self.cores:
      core.run()

    self.thread = Thread(target = self.loop, name = 'CPU #%i' % self.id, priority = 0.0)
    self.thread.start()

  def boot(self, init_states):
    for core in self.cores:
      if init_states:
        core.boot(init_states.pop(0))

import console

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

  if not core.current_suspend_event:
    return

  core.current_suspend_event.set()

def cmd_step(console, cmd):
  """
  Step one instruction forward
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  if not core.current_suspend_event:
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

  if not core.current_suspend_event:
    return

  def __ip_addr(offset = 0):
    return core.CS_ADDR(core.IP().u16 + offset)

  try:
    inst = instructions.decode_instruction(core.MEM_IN32(__ip_addr()))

    if inst.opcode == Opcodes.CALL:
      from debugging import add_breakpoint

      add_breakpoint(core, core.IP().u16 + 4, ephemeral = True)

      if core.current_suspend_event:
        core.current_suspend_event.set()

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
