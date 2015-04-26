import sys

import console
import debugging
import instructions
import machine
import registers
import mm
import profiler

from mm import ADDR_FMT, UINT8_FMT, UINT16_FMT, UINT32_FMT, SEGMENT_SIZE, PAGE_SIZE, i16

from registers import Registers, REGISTER_NAMES
from instructions import Opcodes
from errors import AccessViolationError, InvalidResourceError
from util import debug, info, warn, error, print_table, LRUCache, exception

from ctypes import LittleEndianStructure, c_ubyte, c_ushort

DEFAULT_CPU_SLEEP_QUANTUM = 1.0
DEFAULT_CPU_INST_CACHE_SIZE = 256
DEFAULT_CPU_DATA_CACHE_SIZE = 1024

class InterruptVector(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cs', c_ubyte),
    ('ds', c_ubyte),
    ('ip', c_ushort)
  ]

class CPUException(Exception):
  pass

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

  logger('cs=%s    ds=%s' % (UINT16_FMT(core.registers.cs.value), UINT16_FMT(core.registers.ds.value)))
  logger('fp=%s    sp=%s    ip=%s' % (UINT16_FMT(core.registers.fp.value), UINT16_FMT(core.registers.sp.value), UINT16_FMT(core.registers.ip.value)))
  logger('priv=%i, hwint=%i, e=%i, z=%i, o=%i, s=%i' % (core.registers.flags.privileged, core.registers.flags.hwint, core.registers.flags.e, core.registers.flags.z, core.registers.flags.o, core.registers.flags.s))
  logger('cnt=%s, idle=%s, exit=%i' % (core.registers.cnt.value, core.idle, core.exit_code))

  if hasattr(core, 'math_coprocessor'):
    for index, v in enumerate(core.math_coprocessor.registers.stack):
      logger('MS: %02i: %s', index, UINT32_FMT(v.value))

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
    self.IP = None

  def __getattribute__(self, name):
    if name == 'address':
      return self.DS * SEGMENT_SIZE * PAGE_SIZE + self.FP

    return super(StackFrame, self).__getattribute__(name)

  def __repr__(self):
    return '<StackFrame: CS=%s DS=%s FP=%s IP=%s, (%s)' % (UINT8_FMT(self.CS), UINT8_FMT(self.DS), UINT16_FMT(self.FP), UINT16_FMT(self.IP if self.IP is not None else 0), ADDR_FMT(self.address))

class InstructionCache(LRUCache):
  """
  Simple instruction cache class, based on LRU dictionary, with a limited size.
  """

  def __init__(self, core, size, *args, **kwargs):
    super(InstructionCache, self).__init__(size, *args, **kwargs)

    self.core = core

  def get_object(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param uint24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

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

class CPUCore(machine.MachineWorker):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#%u:#%u: ' % (cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.registers = registers.RegisterSet()

    self.current_ip = None
    self.current_instruction = None

    self.alive = False
    self.running = False
    self.idle = False

    self.core_profiler = profiler.STORE.get_core_profiler(self)

    self.exit_code = 0

    self.frames = []
    self.check_frames = cpu.machine.config.getbool('cpu', 'check-frames', default = False)

    self.debug = debugging.DebuggingSet(self)

    self.opcode_map = {}
    for opcode in Opcodes:
      self.opcode_map[opcode.value] = getattr(self, 'inst_%s' % opcode.name)

    self.instruction_cache = InstructionCache(self, self.cpu.machine.config.getint('cpu', 'inst-cache', default = DEFAULT_CPU_INST_CACHE_SIZE))
    self.data_cache = DataCache(self, self.cpu.machine.config.getint('cpu', 'data-cache', default = DEFAULT_CPU_INST_CACHE_SIZE))

    if self.cpu.machine.config.getbool('cpu', 'math-coprocessor', False):
      import cpu.coprocessor.math_copro

      self.math_coprocessor = cpu.coprocessor.math_copro.MathCoprocessor(self)

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

  def EXCEPTION(self, exc):
    exception(exc, logger = self.ERROR)

    do_log_cpu_core_state(self, logger = self.ERROR)

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

    state.core_states.append(core_state)

  def load_state(self, core_state):
    for reg in REGISTER_NAMES:
      if reg == 'flags':
        self.registers.flags.from_uint16(core_state.flags)

      else:
        self.registers.map[reg].value = getattr(core_state, reg)

    self.exit_code = core_state.exit_code
    self.idle = True if core_state.idle else False

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

    self.current_ip = ip.value

    self.DEBUG('fetch_instruction: cs=%s, ip=%s', self.registers.cs, ip.value)

    inst = self.instruction_cache[self.CS_ADDR(ip.value)]
    ip.value += 4

    return inst

  def reset(self, new_ip = 0):
    """
    Reset core's state. All registers are set to zero, all flags are set to zero,
    except ``HWINT`` flag which is set to one, and ``IP`` is set to requested value.
    Both instruction and data cached are flushed.

    :param uint16 new_ip: new ``IP`` value, defaults to zero
    """

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
    self.data_cache.clear()

  def __symbol_for_ip(self):
    ip = self.registers.ip

    symbol, offset = self.cpu.machine.get_symbol_by_addr(self.registers.cs.value, ip.value)

    if not symbol:
      self.WARN('symbol_for_ip: Unknown jump target: %s', ip)
      return

    self.DEBUG('symbol_for_ip: %s%s (%s)', symbol, ' + %s' % offset if offset != 0 else '', ip.value)

  def backtrace(self):
    bt = []

    if self.check_frames:
      for frame in self.frames:
        symbol, offset = self.cpu.machine.get_symbol_by_addr(frame.CS, frame.IP)
        bt.append((frame.IP, symbol, offset))

      return bt

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
    """
    Push value on stack. ``SP`` is decremented by two, and value is written at this new address.

    :param uint16 val: value to be pushed
    """

    self.registers.sp.value -= 2
    self.data_cache.write_u16(self.DS_ADDR(self.registers.sp.value), val)

  def __raw_pop(self):
    """
    Pop value from stack. 2 byte number is read from address in ``SP``, then ``SP`` is incremented by two.

    :return: popped value
    :rtype: ``uint16``
    """

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
    """
    Create new call stack frame. Push ``IP`` and ``FP`` registers and set ``FP`` value to ``SP``.
    """

    self.DEBUG('__create_frame')

    self.__push(Registers.IP, Registers.FP)

    self.registers.fp.value = self.registers.sp.value

    if self.check_frames:
      self.frames.append(StackFrame(self.registers.cs.value, self.registers.ds.value, self.registers.fp.value))

  def __destroy_frame(self):
    """
    Destroy current call frame. Pop ``FP`` and ``IP`` from stack, by popping ``FP`` restores previous frame.

    :raises CPUException: if current frame does not match last created frame.
    """

    self.DEBUG('__destroy_frame')

    if self.check_frames:
      if self.frames[-1].FP != self.registers.sp.value:
        raise CPUException('Leaving frame with wrong SP: IP=%s, saved SP=%s, current SP=%s' % (ADDR_FMT(self.registers.ip.value), ADDR_FMT(self.frames[-1].FP), ADDR_FMT(self.registers.sp.value)))

      self.frames.pop()

    self.__pop(Registers.FP, Registers.IP)

    self.__symbol_for_ip()

  def __enter_interrupt(self, table_address, index):
    """
    Prepare CPU for handling interrupt routine. New stack is allocated, content fo registers
    is saved onto this new stack, and new call frame is created on this stack. CPU is switched
    into privileged mode. ``CS`` and ``IP`` are set to values, stored in interrupt descriptor
    table at specified offset.

    :param uint24 table_address: address of interrupt descriptor table
    :param int index: interrupt number, its index into IDS
    """

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

    if self.check_frames:
      self.frames[-1].IP = iv.ip

  def __exit_interrupt(self):
    """
    Restore CPU state after running a interrupt routine. Call frame is destroyed, registers
    are restored, stack is returned back to memory pool.
    """

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
    """
    Handle software interrupt. Real software interrupts cause CPU state to be saved
    and new stack and register values are prepared by ``__enter_interrupt`` method,
    virtual interrupts are simply triggered without any prior changes of CPU state.

    :param int index: interrupt number
    """

    self.DEBUG('__do_int: %s', index)

    if index in self.cpu.machine.virtual_interrupts:
      self.DEBUG('__do_int: calling virtual interrupt')

      self.cpu.machine.virtual_interrupts[index].run(self)

      self.DEBUG('__do_int: virtual interrupt finished')

    else:
      self.__enter_interrupt(self.memory.int_table_address, index)

      self.DEBUG('__do_int: CPU state prepared to handle interrupt')

  def __do_irq(self, index):
    """
    Handle hardware interrupt. CPU state is saved and prepared for interrupt routine
    by calling ``__enter_interrupt`` method. Receiving of next another interrupts
    is prevented by clearing ``HWINT`` flag, and ``idle`` flag is set to ``False``.
    """

    self.DEBUG('__do_irq: %s', index)

    self.__enter_interrupt(self.memory.irq_table_address, index)
    self.registers.flags.hwint = 0
    self.idle = False

    self.DEBUG('__do_irq: CPU state prepared to handle IRQ')
    log_cpu_core_state(self)

  def irq(self, index):
    try:
      self.__do_irq(index)

    except (CPUException, ZeroDivisionError, AccessViolationError) as e:
      e.exc_stack = sys.exc_info()
      self.die(e)

  # Do it this way to avoid pylint' confusion
  def __get_privileged(self):
    return self.registers.flags.privileged

  def __set_privileged(self, value):
    self.registers.flags.privileged = value

  privileged = property(__get_privileged, __set_privileged)

  def __check_protected_ins(self):
    """
    Raise ``AccessViolationError`` if core is not running in privileged mode.

    This method should be used by instruction handlers that require privileged mode, e.g. protected instructions.

    :raises AccessViolationError: if the core is not in privileged mode
    """

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
    """
    Set relevant arithmetic flags according to content of registers. Flags are set to zero at the beginning,
    then content of each register is examined, and ``S`` and ``Z`` flags are set.

    ``E`` flag is not touched, ``O`` flag is set to zero.

    :param list regs: list of ``uint16`` registers
    """

    F = self.registers.flags

    F.z = 0
    F.o = 0
    F.s = 0

    for reg in regs:
      if reg.value == 0:
        F.z = 1

      if reg.value & 0x8000 != 0:
        F.s = 1

  def RI_VAL(self, inst):
    return self.registers.map[inst.ireg].value if inst.is_reg == 1 else inst.immediate

  def JUMP(self, inst):
    """
    Change execution flow by modifying IP. Signals profiler that jump was executed.

    :param inst: instruction that caused jump
    """

    if inst.is_reg == 1:
      self.registers.ip.value = self.registers.map[inst.ireg].value
    else:
      self.registers.ip.value += inst.immediate

    self.__symbol_for_ip()

  def CMP(self, x, y, signed = True):
    """
    Compare two numbers, and update relevant flags. Signed comparison is used unless ``signed`` is ``False``.
    All arithmetic flags are set to zero before the relevant ones are set.

    ``O`` flag is reset like the others, therefore caller has to take care of it's setting if it's required
    to set it.

    :param uint16 x: left hand number
    :param uint16 y: right hand number
    :param bool signed: use signed, defaults to ``True``
    """

    F = self.registers.flags

    F.e = 0
    F.z = 0
    F.o = 0
    F.s = 0

    if x == y:
      F.e = 1

      if x == 0:
        F.z = 1

      return

    if signed:
      x = i16(x).value
      y = i16(y).value

    if x < y:
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

    if self.check_frames:
      self.frames[-1].IP = self.registers.ip.value

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

    self.halt()

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
    x = i16(r.value).value
    y = i16(self.RI_VAL(inst)).value
    r.value = x * y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_DIV(self, inst):
    self.check_protected_reg(inst.reg)
    r = self.registers.map[inst.reg]
    x = i16(r.value).value
    y = i16(self.RI_VAL(inst)).value
    r.value = x / y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def inst_MOD(self, inst):
    self.check_protected_reg(inst.reg)
    r = self.registers.map[inst.reg]
    x = i16(r.value).value
    y = i16(self.RI_VAL(inst)).value
    r.value = x % y
    self.__update_arith_flags(self.registers.map[inst.reg])

  def step(self):
    """
    Perform one "step" - fetch next instruction, increment IP, and execute instruction's code (see inst_* methods)
    """

    # pylint: disable-msg=R0912,R0914,R0915
    # "Too many branches"
    # "Too many local variables"
    # "Too many statements"

    self.DEBUG('----- * ----- * ----- * ----- * ----- * ----- * ----- * -----')

    # Read next instruction
    self.DEBUG('"FETCH" phase')

    self.current_instruction = self.fetch_instruction()
    opcode = self.current_instruction.opcode

    self.DEBUG('"EXECUTE" phase: %s %s', UINT16_FMT(self.current_ip), instructions.disassemble_instruction(self.current_instruction))
    log_cpu_core_state(self)

    if opcode not in self.opcode_map:
      raise InvalidOpcodeError(opcode, ip = self.current_ip)

    self.opcode_map[opcode](self.current_instruction)

    cnt = self.registers.cnt
    cnt.value += 1

    self.DEBUG('"SYNC" phase:')
    log_cpu_core_state(self)

    self.core_profiler.take_sample()

  def suspend(self):
    self.DEBUG('CPUCore.suspend')

    self.running = False

  def wake_up(self):
    self.DEBUG('CPUCore.wake_up')

    self.running = True

  def die(self, exc):
    self.DEBUG('CPUCore.die')

    self.exit_code = 1

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('CPUCore.halt')

    self.running = False
    self.alive = False

    self.data_cache.flush()

    log_cpu_core_state(self)

    self.cpu.machine.reactor.remove_task(self)

    self.INFO('Halted')

  def runnable(self):
    return self.alive and self.running

  def run(self):
    try:
      self.step()

    except (CPUException, ZeroDivisionError, AccessViolationError) as e:
      e.exc_stack = sys.exc_info()
      self.die(e)

  def boot(self, init_state):
    self.DEBUG('Booting...')

    self.reset()

    cs, ds, sp, ip, privileged = init_state

    self.registers.cs.value = cs
    self.registers.ds.value = ds
    self.registers.ip.value = ip
    self.registers.sp.value = sp
    self.registers.fp.value = sp
    self.registers.flags.privileged = 1 if privileged else 0

    log_cpu_core_state(self)

    self.alive = True
    self.running = True

    self.cpu.machine.reactor.add_task(self)

    self.INFO('Booted')

class CPU(machine.MachineWorker):
  def __init__(self, machine, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#%i:' % cpuid

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()

    self.cores = []
    for i in xrange(0, cores):
      __core = CPUCore(i, self, self.memory)
      self.cores.append(__core)

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

  def EXCEPTION(self, exc):
    exception(exc, logger = self.ERROR)

  def living_cores(self):
    return (__core for __core in self.cores if __core.alive is True)

  def halted_cores(self):
    return (__core for __core in self.cores if __core.alive is not True)

  def running_cores(self):
    return (__core for __core in self.cores if __core.running is True)

  def suspended_cores(self):
    return (__core for __core in self.cores if __core.running is not True)

  def suspend(self):
    self.DEBUG('CPU.suspend')

    map(lambda __core: __core.suspend(), self.running_cores())

  def wake_up(self):
    self.DEBUG('CPU.wake_up')

    map(lambda __core: __core.wake_up(), self.suspended_cores())

  def die(self, exc):
    self.DEBUG('CPU.die')

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('CPU.halt')

    map(lambda __core: __core.halt(), self.living_cores())

  def boot(self, init_states):
    self.INFO('Booting...')

    for core in self.cores:
      if init_states:
        core.boot(init_states.pop(0))

    self.INFO('Booted')

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
