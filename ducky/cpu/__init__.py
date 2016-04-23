import functools
import sys

from six import iterkeys, itervalues, iteritems
from six.moves import range

from functools import partial

from . import registers
from .. import profiler

from ..interfaces import IMachineWorker, ISnapshotable
from ..mm import UINT8_FMT, UINT16_FMT, UINT32_FMT, PAGE_SIZE, PAGE_MASK, PAGE_SHIFT, PageTableEntry, UINT64_FMT
from .registers import Registers, REGISTER_NAMES, FLAGS
from .instructions import DuckyInstructionSet
from ..errors import AccessViolationError, InvalidResourceError
from ..util import LRUCache, Flags
from ..snapshot import SnapshotNode
from ..devices import IRQList

#: Default IVT address
DEFAULT_IVT_ADDRESS = 0x00000000

#: Default PT address
DEFAULT_PT_ADDRESS = 0x00010000

#: Default size of core instruction cache, in instructions.
DEFAULT_CORE_INST_CACHE_SIZE = 256

class CPUState(SnapshotNode):
  def get_core_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('core')]

  def get_core_state_by_id(self, coreid):
    return self.get_children()['core{}'.format(coreid)]

class CPUCoreState(SnapshotNode):
  def __init__(self):
    super(CPUCoreState, self).__init__('cpuid', 'coreid', 'registers', 'exit_code', 'alive', 'running', 'idle', 'ivt_address', 'pt_address', 'pt_enabled', 'flags')

class InterruptVector(object):
  """
  Interrupt vector table entry.
  """

  SIZE = 8

  def __init__(self, ip = 0x0000, sp = 0x0000):
    self.ip = ip
    self.sp = sp

  def __repr__(self):
    return '<InterruptVector: ip=%s, sp=%s>' % (UINT32_FMT(self.ip), UINT32_FMT(self.sp))

class CPUException(Exception):
  """
  Base class for CPU-related exceptions.

  :param string msg: message describing exceptional state.
  :param ducky.cpu.CPUCore core: CPU core that raised exception, if any.
  :param u32_t ip: address of an instruction that caused exception, if any.
  """

  def __init__(self, msg, core = None, ip = None):
    super(CPUException, self).__init__(msg)

    self.core = core
    self.ip = ip

class InvalidOpcodeError(CPUException):
  """
  Raised when unknown or invalid opcode is found in instruction.

  :param int opcode: wrong opcode.
  """

  def __init__(self, opcode, *args, **kwargs):
    super(InvalidOpcodeError, self).__init__('Invalid opcode: opcode={}'.format(opcode), *args, **kwargs)

    self.opcode = opcode

class InvalidInstructionSetError(CPUException):
  """
  Raised when switch to unknown or invalid instruction set is requested.

  :param int inst_set: instruction set id.
  """

  def __init__(self, inst_set, *args, **kwargs):
    super(InvalidInstructionSetError, self).__init__('Invalid instruction set requested: inst_set={}'.format(inst_set), *args, **kwargs)

    self.inst_set = inst_set

def do_log_cpu_core_state(core, logger = None, disassemble = True, inst_set = None):
  """
  Log state of a CPU core. Content of its registers, and other interesting or
  useful internal variables are logged.

  :param ducky.cpu.CPUCore core: core whose state should be logged.
  :param logger: called for each line of output to actualy log it. By default,
    core's :py:meth:`ducky.cpu.CPUCore.DEBUG` method is used.
  """

  logger = logger or core.DEBUG
  inst_set = inst_set or core.instruction_set

  for i in range(0, Registers.REGISTER_SPECIAL, 4):
    regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
    s = ['r{:02d}={}'.format(reg, UINT32_FMT(core.registers.map[reg].value)) for reg in regs]
    logger(' '.join(s))

  logger('fp=%s    sp=%s    ip=%s', UINT32_FMT(core.registers.fp.value), UINT32_FMT(core.registers.sp.value), UINT32_FMT(core.registers.ip.value))
  logger('flags=%s', core.flags.to_string())
  logger('cnt=%s, alive=%s, running=%s, idle=%s, exit=%i', core.registers.cnt.value, core.alive, core.running, core.idle, core.exit_code)

  if hasattr(core, 'math_coprocessor'):
    for index, v in enumerate(core.math_coprocessor.registers.stack):
      logger('MC: %02i: %s', index, UINT64_FMT(v.value))

  if hasattr(core, 'control_coprocessor'):
    cp = core.control_coprocessor
    logger('CC: cr0=%s, cr1=%s, cr2=%s, cr3=%s', UINT32_FMT(cp.read_cr0()), UINT32_FMT(cp.read_cr1()), UINT32_FMT(cp.read_cr2()), UINT32_FMT(cp.read_cr3()))

  if disassemble is True:
    if core.current_instruction is not None:
      inst = inst_set.disassemble_instruction(core.LOGGER, core.current_instruction)
      logger('inst-set=%02d current=%s', inst_set.instruction_set_id, inst)
    else:
      logger('inst-set=%02d current=<none>', inst_set.instruction_set_id)
  else:
    logger('inst-set=%02d current=<unknown>', inst_set.instruction_set_id)

  for index, frame in enumerate(core.backtrace()):
    logger('Frame #%i: %s', index, frame)

def log_cpu_core_state(*args, **kwargs):
  """
  This is a wrapper for ducky.cpu.do_log_cpu_core_state function. Its main
  purpose is to be removed when debug mode is not set, therefore all debug
  calls of ducky.cpu.do_log_cpu_core_state will disappear from code,
  making such code effectively "quiet".
  """

  do_log_cpu_core_state(*args, **kwargs)

class StackFrame(object):
  def __init__(self, fp):
    super(StackFrame, self).__init__()

    self.FP = fp
    self.IP = None

  def __getattribute__(self, name):
    if name == 'address':
      return self.FP

    return super(StackFrame, self).__getattribute__(name)

  def __repr__(self):
    return '<StackFrame: FP={}, IP={}>'.format(UINT32_FMT(self.FP), UINT32_FMT(self.IP if self.IP is not None else 0))


class CoreFlags(Flags):
  _flags = ['privileged', 'hwint_allowed', 'equal', 'zero', 'overflow', 'sign']
  _labels = 'PHEZOS'


class InstructionCache(LRUCache):
  """
  Simple instruction cache class, based on LRU dictionary, with a limited size.

  :param ducky.cpu.CPUCore core: CPU core that owns this cache.
  :param int size: maximal number of entries this cache can store.
  """

  def __init__(self, mmu, size, *args, **kwargs):
    super(InstructionCache, self).__init__(mmu.core.cpu.machine.LOGGER, size, *args, **kwargs)

    self.mmu = mmu
    self.core = mmu.core

    if mmu.core.cpu.machine.config.getbool('machine', 'jit', False):
      self.get_object = self.get_object_jit

  def get_object(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param u24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

    core = self.core

    inst, desc, opcode = core.instruction_set.decode_instruction(core.LOGGER, core.MEM_IN32(addr, not_execute = False), core = core)
    return inst, opcode, partial(desc.execute, core, inst)

  def get_object_jit(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param u24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

    core = self.core

    inst, desc, opcode = core.instruction_set.decode_instruction(core.LOGGER, core.MEM_IN32(addr, not_execute = False), core = core)

    fn = desc.jit(core, inst)

    if fn is None:
      return inst, opcode, partial(desc.execute, core, inst)

    return inst, opcode, fn

class MMU(ISnapshotable):
  """
  Memory management unit (aka MMU) provides a single point handling all core's memory operations.
  All memory reads and writes must go through this unit, which is then responsible for all
  translations, access control, and caching.

  :param ducky.cpu.CPUCore core: parent core.
  :param ducky.mm.MemoryController memory_controller: memory controller that provides access
    to the main memory.
  """

  def __init__(self, core, memory_controller):
    super(MMU, self).__init__()

    config = core.cpu.machine.config

    self.core = core
    self.memory = memory_controller

    self.force_aligned_access = config.getbool('memory', 'force-aligned-access', default = False)
    self.pt_address = config.getint('cpu', 'pt-address', DEFAULT_PT_ADDRESS)

    self.pt_enabled = False

    self.pte_cache = {}

    self.DEBUG = core.DEBUG

    self.instruction_cache = InstructionCache(self, config.getint('cpu', 'inst-cache', default = DEFAULT_CORE_INST_CACHE_SIZE))

    self.set_access_methods()

  def __debug_wrapper_read(self, reader, *args, **kwargs):
    self.core.debug.pre_memory(args[0], read = True)

    if not self.core.running:
      return

    value = reader(*args, **kwargs)

    self.core.debug.post_memory(args[0], read = True)

    return value

  def __debug_wrapper_write(self, writer, *args, **kwargs):
    self.core.debug.pre_memory(args[0], read = False)

    if not self.core.running:
      return

    writer(*args, **kwargs)

    self.core.debug.post_memory(args[0], read = False)

  def set_access_methods(self):
    """
    Set parent core's memory-access methods to proper shortcuts.
    """

    self.DEBUG('MMU.set_access_methods')

    self.core.MEM_IN8   = self.full_read_u8
    self.core.MEM_IN16  = self.full_read_u16
    self.core.MEM_IN32  = self.full_read_u32
    self.core.MEM_OUT8  = self.full_write_u8
    self.core.MEM_OUT16 = self.full_write_u16
    self.core.MEM_OUT32 = self.full_write_u32

    if self.core.debug is not None:
      self.core.MEM_IN8   = partial(self.__debug_wrapper_read,  self.core.MEM_IN8)
      self.core.MEM_IN16  = partial(self.__debug_wrapper_read,  self.core.MEM_IN16)
      self.core.MEM_IN32  = partial(self.__debug_wrapper_read,  self.core.MEM_IN32)
      self.core.MEM_OUT8  = partial(self.__debug_wrapper_write, self.core.MEM_OUT8)
      self.core.MEM_OUT16 = partial(self.__debug_wrapper_write, self.core.MEM_OUT16)
      self.core.MEM_OUT32 = partial(self.__debug_wrapper_write, self.core.MEM_OUT32)

  def reset(self):
    self.instruction_cache.clear()

    self.pt_enabled = False
    self.pte_cache = {}

  def halt(self):
    pass

  def release_ptes(self):
    self.DEBUG('MMU.release_ptes')

    self.pte_cache = {}

  def get_pte(self, addr):
    """
    Find out PTE for particular physical address. If PTE is not in internal PTE cache, it is
    fetched from PTE table.

    :param u24 addr: memory address.
    """

    pg_index = (addr & PAGE_MASK) >> PAGE_SHIFT

    self.DEBUG('MMU.get_pte: addr=%s, pte-address=%s', UINT32_FMT(addr), UINT32_FMT(self.pt_address + pg_index))

    if pg_index not in self.pte_cache:
      self.pte_cache[pg_index] = pte = PageTableEntry.from_int(self.memory.read_u8(self.pt_address + pg_index))

    else:
      pte = self.pte_cache[pg_index]

    self.DEBUG('  pte=%s (%s)', pte.to_string(), pte.to_int())

    return pte

  def check_access(self, access, addr, align = None):
    """
    Check attempted access against PTE. Be aware that each check can be turned off by configuration file.

    :param access: ``read``, ``write`` or ``execute``.
    :param u24 addr: memory address.
    :param int align: if set, operation is expected to be aligned to this boundary.
    :raises ducky.errors.AccessViolationError: when access is denied.
    """

    self.DEBUG('MMU.check_access: access=%s, addr=%s', access, UINT32_FMT(addr))

    if self.force_aligned_access and align is not None and addr % align:
      raise AccessViolationError('Not allowed to access unaligned memory: access=%s, address=%s, align=%s' % (access, UINT32_FMT(addr), align))

    pg_index = (addr & PAGE_MASK) >> PAGE_SHIFT

    if self.core.privileged or self.pt_enabled is not True:
      return self.memory.get_page(pg_index)

    pte = self.get_pte(addr)

    if getattr(pte, access) == 1:
      return self.memory.get_page(pg_index)

    raise AccessViolationError('Not allowed to access memory: access=%s, address=%s, pte=%s' % (access, UINT32_FMT(addr), pte.to_string()))

  def full_read_u8(self, addr):
    self.DEBUG('MMU.raw_read_u8: addr=%s', UINT32_FMT(addr))

    return self.check_access('read', addr).read_u8(addr & (PAGE_SIZE - 1))

  def full_read_u16(self, addr):
    self.DEBUG('MMU.raw_read_u16: addr=%s', UINT32_FMT(addr))

    return self.check_access('read', addr, align = 2).read_u16(addr & (PAGE_SIZE - 1))

  def full_read_u32(self, addr, not_execute = True):
    self.DEBUG('MMU.raw_read_u32: addr=%s', UINT32_FMT(addr))

    pg = self.check_access('read', addr, align = 4)

    if not_execute is not True:
      pg = self.check_access('execute', addr)

    return pg.read_u32(addr & (PAGE_SIZE - 1))

  def full_write_u8(self, addr, value):
    self.DEBUG('MMU.raw_write_u8: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    return self.check_access('write', addr).write_u8(addr & (PAGE_SIZE - 1), value)

  def full_write_u16(self, addr, value):
    self.DEBUG('MMU.raw_write_u16: addr=%s, value=%s', UINT32_FMT(addr), UINT16_FMT(value))

    return self.check_access('write', addr).write_u16(addr & (PAGE_SIZE - 1), value)

  def full_write_u32(self, addr, value):
    self.DEBUG('MMU.raw_write_u32: addr=%s, value=%s', UINT32_FMT(addr), UINT32_FMT(value))

    return self.check_access('write', addr).write_u32(addr & (PAGE_SIZE - 1), value)

class CPUCore(ISnapshotable, IMachineWorker):
  """
  This class represents the main workhorse, one of CPU cores. Reads
  instructions, executes them, has registers, caches, handles interrupts,
  ...

  :param int coreid: id of this core. Usually, it's its serial number but it
    has no special meaning.
  :param ducky.cpu.CPU cpu: CPU that owns this core.
  :param ducky.mm.MemoryController memory_controller: use this controller to
    access main memory.
  """

  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    config = cpu.machine.config

    self.cpuid = '#{}:#{}'.format(cpu.id, coreid)
    self.cpuid_prefix = self.cpuid + ':'

    def __log(logger, *args, **kwargs):
      args = ('%s ' + args[0],) + (self.cpuid_prefix,) + args[1:]
      logger(*args)

    def __log_exception(logger_fn, exc):
      self.cpu.machine.LOGGER.exception('Exception raised in CPU core')
      do_log_cpu_core_state(self, logger = logger_fn, disassemble = False if isinstance(exc, InvalidOpcodeError) else True)

    self.LOGGER = cpu.machine.LOGGER
    self.DEBUG = lambda *args, **kwargs: __log(self.cpu.machine.DEBUG, *args, **kwargs)
    self.INFO  = lambda *args, **kwargs: __log(self.cpu.machine.INFO, *args, **kwargs)
    self.WARN  = lambda *args, **kwargs: __log(self.cpu.machine.WARN, *args, **kwargs)
    self.ERROR = lambda *args, **kwargs: __log(self.cpu.machine.ERROR, *args, **kwargs)
    self.EXCEPTION = functools.partial(__log_exception, self.ERROR)

    self.id = coreid
    self.cpu = cpu

    self.debug = None

    self.mmu = MMU(self, memory_controller)

    self.registers = registers.RegisterSet()

    self.privileged = True
    self.hwint_allowed = False

    self.arith_equal = False
    self.arith_zero = False
    self.arith_overflow = False
    self.arith_sign = False

    self.ivt_address = config.getint('cpu', 'ivt-address', DEFAULT_IVT_ADDRESS)

    self.instruction_set = DuckyInstructionSet
    self.instruction_set_stack = []

    self.current_ip = None
    self.current_instruction = None

    self.alive = False
    self.running = False
    self.idle = False

    self.core_profiler = profiler.STORE.get_core_profiler(self) if profiler.STORE.is_cpu_enabled() else None

    self.exit_code = 0

    self.frames = []
    self.check_frames = cpu.machine.config.getbool('cpu', 'check-frames', default = False)

    self.coprocessors = {}

    if self.cpu.machine.config.getbool('cpu', 'math-coprocessor', False):
      from .coprocessor import math_copro

      self.math_coprocessor = self.coprocessors['math'] = math_copro.MathCoprocessor(self)

    if config.getbool('cpu', 'control-coprocessor', True):
      from .coprocessor import control
      self.control_coprocessor = self.coprocessors['control'] = control.ControlCoprocessor(self)

  def has_coprocessor(self, name):
    return hasattr(self, '{}_coprocessor'.format(name))

  def __repr__(self):
    return '#{}:#{}'.format(self.cpu.id, self.id)

  def save_state(self, parent):
    self.DEBUG('save_state')

    state = parent.add_child('core{}'.format(self.id), CPUCoreState())

    state.cpuid = self.cpu.id
    state.coreid = self.id

    state.flags = self.flags.to_int()

    state.registers = []

    for i, reg in enumerate(REGISTER_NAMES):
      state.registers.append(int(self.registers.map[reg].value))

    state.ivt_address = self.ivt_address
    state.pt_address = self.mmu.pt_address
    state.pt_enabled = self.mmu.pt_enabled

    state.exit_code = self.exit_code
    state.idle = self.idle
    state.alive = self.alive
    state.running = self.running

    if self.has_coprocessor('math'):
      self.math_coprocessor.save_state(state)

  def load_state(self, state):
    self.flags = CoreFlags.from_int(state.flags)

    for i, reg in enumerate(REGISTER_NAMES):
      self.registers.map[reg].value = state.registers[i]

    self.ivt_address = state.ivt_address
    self.mmu.pt_address = state.pt_address
    self.mmu.pt_enabled = state.pt_enabled

    self.exit_code = state.exit_code
    self.idle = state.idle
    self.alive = state.alive
    self.running = state.running

    if self.has_coprocessor('math'):
      self.math_coprocessor.load_state(state.get_children()['math_coprocessor'])

  def init_debug_set(self):
    if self.debug is None:
      from .. import debugging
      self.debug = debugging.DebuggingSet(self)

      self.mmu.set_access_methods()

  def REG(self, reg):
    return self.registers.map[reg]

  def IP(self):
    return self.registers.ip

  def SP(self):
    return self.registers.sp

  def FP(self):
    return self.registers.fp

  def reset(self, new_ip = 0x00000000):
    """
    Reset core's state. All registers are set to zero, all flags are set to zero,
    except ``HWINT`` flag which is set to one, and ``IP`` is set to requested value.

    :param u32_t new_ip: new ``IP`` value, defaults to zero
    """

    self.instruction_set = DuckyInstructionSet
    self.instruction_set_stack = []

    for reg in registers.RESETABLE_REGISTERS:
      self.REG(reg).value = 0

    self.flags = CoreFlags.create(privileged = True)

    self.registers.ip.value = new_ip

    self.mmu.reset()

  def backtrace(self):
    bt = []

    if self.check_frames:
      for frame in self.frames:
        bt.append(repr(frame))

      return bt

    bt = []

    for frame_index, frame in enumerate(self.frames):
      ip = self.mmu.memory.read_u32(frame.address + 4)
      bt.append(ip)

    ip = self.registers.ip.value - 4
    bt.append(ip)

    return bt

  def raw_push(self, val):
    """
    Push value on stack. ``SP`` is decremented by four, and value is written at this new address.

    :param u32 val: value to be pushed
    """

    self.DEBUG("raw_push: sp=%s, value=%s", UINT32_FMT(self.registers.sp.value), UINT32_FMT(val))

    self.registers.sp.value -= 4
    self.MEM_OUT32(self.registers.sp.value, val)

  def raw_pop(self):
    """
    Pop value from stack. 4 byte number is read from address in ``SP``, then ``SP`` is incremented by four.

    :return: popped value
    :rtype: ``u32``
    """

    ret = self.MEM_IN32(self.registers.sp.value)
    self.registers.sp.value += 4
    return ret

  def push(self, *regs):
    for reg_id in regs:
      value = self.flags.to_int() if reg_id == FLAGS else self.registers.map[reg_id].value

      self.DEBUG('push: %s (%s) at %s', reg_id, UINT32_FMT(value), UINT32_FMT(self.registers.sp.value - 4))
      self.raw_push(value)

  def pop(self, *regs):
    for reg_id in regs:
      value = self.raw_pop()

      if reg_id == FLAGS:
        self.flags = CoreFlags.from_int(value)

      else:
        self.registers.map[reg_id].value = value

      self.DEBUG('pop: %s (%s) from %s', reg_id, UINT32_FMT(value), UINT32_FMT(self.registers.sp.value - 4))

  def create_frame(self):
    """
    Create new call stack frame. Push ``IP`` and ``FP`` registers and set ``FP`` value to ``SP``.
    """

    self.DEBUG('create_frame')

    self.push(Registers.IP, Registers.FP)

    self.registers.fp.value = self.registers.sp.value

    if self.check_frames:
      self.frames.append(StackFrame(self.registers.fp.value))

  def destroy_frame(self):
    """
    Destroy current call frame. Pop ``FP`` and ``IP`` from stack, by popping ``FP`` restores previous frame.

    :raises CPUException: if current frame does not match last created frame.
    """

    self.DEBUG('destroy_frame')

    if self.check_frames:
      if self.frames[-1].FP != self.registers.sp.value:
        raise CPUException('Leaving frame with wrong SP: IP={}, saved SP={}, current SP={}'.format(UINT32_FMT(self.registers.ip.value), UINT32_FMT(self.frames[-1].FP), UINT32_FMT(self.registers.sp.value)))

      self.frames.pop()

    self.pop(Registers.FP, Registers.IP)

  def __load_interrupt_vector(self, index):
    self.DEBUG('load_interrupt_vector: ivt=%s, index=%i', UINT32_FMT(self.ivt_address), index)

    desc = InterruptVector()

    vector_address = self.ivt_address + index * InterruptVector.SIZE

    desc.ip = self.MEM_IN32(vector_address)
    desc.sp = self.MEM_IN32(vector_address + 4)

    return desc

  def __enter_interrupt(self, index):
    """
    Prepare CPU for handling interrupt routine. New stack is allocated, content fo registers
    is saved onto this new stack, and new call frame is created on this stack. CPU is switched
    into privileged mode. ``CS`` and ``IP`` are set to values, stored in interrupt descriptor
    table at specified offset.

    :param u24 table_address: address of interrupt descriptor table
    :param int index: interrupt number, its index into IDS
    """

    self.DEBUG('__enter_interrupt: index=%i', index)

    if index >= IRQList.IRQ_COUNT:
      raise InvalidResourceError('Interrupt index out of range: index=%d' % index)

    iv = self.__load_interrupt_vector(index)

    self.DEBUG('__enter_interrupt: desc=%s', iv)

    old_SP = self.registers.sp.value

    self.registers.sp.value = iv.sp

    self.raw_push(old_SP)
    self.push(FLAGS)
    self.create_frame()

    self.privileged = True

    self.registers.ip.value = iv.ip

    if self.check_frames:
      self.frames[-1].IP = iv.ip

    self.instruction_set_stack.append(self.instruction_set)
    self.instruction_set = DuckyInstructionSet

  def exit_interrupt(self):
    """
    Restore CPU state after running a interrupt routine. Call frame is destroyed, registers
    are restored, stack is returned back to memory pool.
    """

    self.DEBUG('exit_interrupt')

    self.destroy_frame()
    self.pop(FLAGS)

    old_SP = self.raw_pop()

    self.registers.sp.value = old_SP

    self.instruction_set = self.instruction_set_stack.pop(0)

  def do_int(self, index):
    """
    Handle software interrupt. Real software interrupts cause CPU state to be saved
    and new stack and register values are prepared by ``__enter_interrupt`` method,
    virtual interrupts are simply triggered without any prior changes of CPU state.

    :param int index: interrupt number
    """

    self.DEBUG('do_int: %s', index)

    if index in self.cpu.machine.virtual_interrupts:
      self.DEBUG('do_int: calling virtual interrupt')

      self.cpu.machine.virtual_interrupts[index].run(self)

      self.DEBUG('do_int: virtual interrupt finished')

    else:
      self.__enter_interrupt(index)

      self.DEBUG('do_int: CPU state prepared to handle interrupt')

  def __do_irq(self, index):
    """
    Handle hardware interrupt. CPU state is saved and prepared for interrupt routine
    by calling ``__enter_interrupt`` method. Receiving of next another interrupts
    is prevented by clearing ``HWINT`` flag, and ``idle`` flag is set to ``False``.
    """

    self.DEBUG('__do_irq: %s', index)

    self.__enter_interrupt(index)
    self.hwint_allowed = False
    self.change_runnable_state(idle = False)

    self.DEBUG('__do_irq: CPU state prepared to handle IRQ')
    log_cpu_core_state(self, inst_set = self.instruction_set_stack[-1])

  def irq(self, index):
    try:
      self.__do_irq(index)

    except (CPUException, ZeroDivisionError, AccessViolationError) as e:
      e.exc_stack = sys.exc_info()
      self.die(e)

  def __get_flags(self):
    return CoreFlags.create(privileged = self.privileged, hwint_allowed = self.hwint_allowed, equal = self.arith_equal, zero = self.arith_zero, overflow = self.arith_overflow, sign = self.arith_sign)

  def __set_flags(self, flags):
    self.privileged = flags.privileged
    self.hwint_allowed = flags.hwint_allowed
    self.arith_equal = flags.equal
    self.arith_zero = flags.zero
    self.arith_overflow = flags.overflow
    self.arith_sign = flags.sign

  flags = property(__get_flags, __set_flags)

  def check_protected_ins(self):
    """
    Raise ``AccessViolationError`` if core is not running in privileged mode.

    This method should be used by instruction handlers that require privileged mode, e.g. protected instructions.

    :raises AccessViolationError: if the core is not in privileged mode
    """

    if not self.privileged:
      raise AccessViolationError('Instruction not allowed in unprivileged mode: inst={}'.format(self.current_instruction))

  def check_protected_port(self, port):
    if port not in self.cpu.machine.ports:
      raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

    if self.privileged:
      return

    if self.cpu.machine.ports[port].is_port_protected(port):
      raise AccessViolationError('Access to port not allowed in unprivileged mode: inst={}, port={}'.format(self.current_instruction, port))

  def step(self):
    """
    Perform one "step" - fetch next instruction, increment IP, and execute instruction's code (see inst_* methods)
    """

    self.DEBUG('----- * ----- * ----- * ----- * ----- * ----- * ----- * -----')

    has_debug = self.debug is not None

    if has_debug:
      self.debug.pre_step()

      if not self.running:
        return

    # Read next instruction
    self.DEBUG('"FETCH" phase')

    ip = self.registers.ip
    self.current_ip = ip.value

    self.DEBUG('fetch instruction: ip=%s', UINT32_FMT(ip.value))

    try:
      self.current_instruction, opcode, execute = self.mmu.instruction_cache[ip.value]
      ip.value += 4

      self.DEBUG('"EXECUTE" phase: %s %s', UINT32_FMT(self.current_ip), self.instruction_set.disassemble_instruction(self.LOGGER, self.current_instruction))
      log_cpu_core_state(self)

      execute()

    except (InvalidOpcodeError, AccessViolationError, InvalidResourceError) as e:
      self.die(e)
      return

    cnt = self.registers.cnt
    cnt.value += 1

    self.DEBUG('"SYNC" phase:')
    log_cpu_core_state(self)

    if self.core_profiler is not None:
      self.core_profiler.take_sample()

    if has_debug:
      self.debug.post_step()

  def change_runnable_state(self, alive = None, running = None, idle = None):
    old_state = self.alive and self.running and not self.idle

    if alive is not None:
      self.alive = alive

    if running is not None:
      self.running = running

    if idle is not None:
      self.idle = idle

    new_state = self.alive and self.running and not self.idle

    if old_state != new_state:
      if new_state is True:
        self.cpu.machine.reactor.task_runnable(self)

      else:
        self.cpu.machine.reactor.task_suspended(self)

  def suspend(self):
    self.DEBUG('CPUCore.suspend')

    self.change_runnable_state(running = False)
    self.cpu.machine.events.trigger('on-core-suspend', self)

  def wake_up(self):
    self.DEBUG('CPUCore.wake_up')

    self.change_runnable_state(running = True)
    self.cpu.machine.events.trigger('on-core-running', self)

  def die(self, exc):
    self.DEBUG('CPUCore.die')

    self.exit_code = 1

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('CPUCore.halt')

    self.cpu.machine.events.trigger('on-core-suspended', self)
    self.cpu.machine.events.trigger('on-core-halted', self)

    self.mmu.halt()

    self.change_runnable_state(alive = False, running = False)

    log_cpu_core_state(self)

    self.cpu.machine.reactor.remove_task(self)

    self.cpu.machine.tenh('%r: CPU core halted', self)

  def run(self):
    try:
      self.step()

    except (CPUException, ZeroDivisionError, AccessViolationError) as e:
      e.exc_stack = sys.exc_info()
      self.die(e)

    except Exception as e:
      e.exc_stack = sys.exc_info()
      self.die(e)

  def boot(self):
    self.DEBUG('CPUCore.boot')

    from ..boot import DEFAULT_BOOTLOADER_ADDRESS

    self.reset(new_ip = DEFAULT_BOOTLOADER_ADDRESS)

    log_cpu_core_state(self)

    self.cpu.machine.reactor.add_task(self)
    self.change_runnable_state(alive = True, running = True)
    self.cpu.machine.events.trigger('on-core-alive', self)
    self.cpu.machine.events.trigger('on-core-running', self)

    if self.core_profiler is not None:
      self.core_profiler.enable()

    self.cpu.machine.tenh('%r: CPU core is up', self)
    if self.mmu.instruction_cache is not None:
      self.cpu.machine.tenh('%r:  %d IC slots', self, self.mmu.instruction_cache.size)
    self.cpu.machine.tenh('%r:  check-frames: %s', self, 'yes' if self.check_frames else 'no')
    if self.coprocessors:
      self.cpu.machine.tenh('%r:  coprocessor: %s', self, ' '.join(sorted(iterkeys(self.coprocessors))))

class CPU(ISnapshotable, IMachineWorker):
  def __init__(self, machine, cpuid, memory_controller, cores = 1):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#{}:'.format(cpuid)

    def __log(logger, *args):
      args = ('%s ' + args[0],) + (self.cpuid_prefix,) + args[1:]
      logger(*args)

    self.DEBUG = lambda *args: __log(self.machine.DEBUG, *args)
    self.INFO  = lambda *args: __log(self.machine.INFO, *args)
    self.WARN  = lambda *args: __log(self.machine.WARN, *args)
    self.ERROR = lambda *args: __log(self.machine.ERROR, *args)
    self.EXCEPTION = lambda *args: __log(self.machine.EXCEPTION, *args)

    self.machine = machine
    self.id = cpuid

    self.cores = []
    self.living_cores = []
    self.halted_cores = []
    self.running_cores = []
    self.suspended_cores = []

    for i in range(0, cores):
      __core = CPUCore(i, self, memory_controller)
      self.cores.append(__core)

      self.halted_cores.append(__core)
      self.suspended_cores.append(__core)

    self.machine.console.register_commands([
      ('sc', cmd_set_core),
      ('st', cmd_core_state),
      ('cont', cmd_cont),
      ('step', cmd_step),
    ])

  def __repr__(self):
    return '#%i' % self.id

  def save_state(self, parent):
    state = parent.add_child('cpu{}'.format(self.id), CPUState())

    for core in self.cores:
      core.save_state(state)

  def load_state(self, state):
    for core_state in itervalues(state.get_children()):
      self.cores[core_state.coreid].load_state(core_state)

  def on_core_alive(self, core):
    """
    Triggered when one of cores goes alive.
    """

    self.DEBUG('%s.on_core_alive: core=%s', self.__class__.__name__, core)

    if core.cpu != self:
      return

    self.halted_cores.remove(core)
    self.living_cores.append(core)

  def on_core_halted(self, core):
    """
    Signal CPU that one of cores is no longer alive.
    """

    self.DEBUG('%s.on_core_halted: core=%s', self.__class__.__name__, core)

    if core.cpu != self:
      return

    self.living_cores.remove(core)
    self.halted_cores.append(core)

  def on_core_running(self, core):
    """
    Signal CPU that one of cores is now running.
    """

    self.DEBUG('%s.on_core_running: core=%s', self.__class__.__name__, core)

    if core.cpu != self:
      return

    self.suspended_cores.remove(core)
    self.running_cores.append(core)

  def on_core_suspended(self, core):
    """
    Signal CPU that one of cores is now suspended.
    """

    self.DEBUG('%s.on_core_suspended: core=%s', self.__class__.__name__, core)

    if core.cpu != self:
      return

    self.running_cores.remove(core)
    self.suspended_cores.append(core)

  def suspend(self):
    self.DEBUG('CPU.suspend')

    for core in self.running_cores:
      core.suspend()

  def wake_up(self):
    self.DEBUG('CPU.wake_up')

    for core in self.suspended_cores:
      core.wake_up()

  def die(self, exc):
    self.DEBUG('CPU.die')

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('CPU.halt')

    for core in self.living_cores:
      core.halt()

    self.machine.events.remove_listener('on-core-alive', self.on_core_alive)
    self.machine.events.remove_listener('on-core-halted', self.on_core_halted)
    self.machine.events.remove_listener('on-core-running', self.on_core_running)
    self.machine.events.remove_listener('on-core-suspended', self.on_core_suspended)

    self.machine.tenh('%r: CPU halted', self)

  def boot(self):
    self.DEBUG('CPU.boot')

    self.machine.events.add_listener('on-core-alive', self.on_core_alive)
    self.machine.events.add_listener('on-core-halted', self.on_core_halted)
    self.machine.events.add_listener('on-core-running', self.on_core_running)
    self.machine.events.add_listener('on-core-suspended', self.on_core_suspended)

    for core in self.cores:
      core.boot()

    self.machine.tenh('%r: CPU is up', self)

def cmd_set_core(console, cmd):
  """
  Set core address of default core used by control commands: sc <coreid>
  """

  M = console.master.machine

  try:
    core = M.core(cmd[1])

  except InvalidResourceError:
    console.writeln('go away')
    return

  console.default_core = core

  console.writeln('# OK: default core is %s', core.cpuid)

def cmd_cont(console, cmd):
  """
  Continue execution until next breakpoint is reached: cont
  """

  if console.default_core is None:
    console.writeln('# ERR: no core selected')
    return

  if console.default_core.running:
    console.writeln('# ERR: core is not suspended')
    return

  console.default_core.wake_up()

  console.writeln('# OK')

def cmd_step(console, cmd):
  """
  Step one instruction forward
  """

  if console.default_core is None:
    console.writeln('# ERR: no core selected')
    return

  if console.default_core.running:
    console.writeln('# ERR: core is not suspended')
    return

  console.default_core.run()

  console.writeln('# OK')

def cmd_next(console, cmd):
  """
  Proceed to the next instruction in the same stack frame.
  """

  core = console.default_core if hasattr(console, 'default_core') else console.machine.cpus[0].cores[0]

  if not core.is_suspended():
    return

  def __ip_addr(offset = 0):
    return core.registers.ip.value + offset

  try:
    inst = core.instruction_set.decode_instruction(core.LOGGER, core.memory.read_u32(__ip_addr()))

    if inst.opcode == core.instruction_set.opcodes.CALL:
      from ..debugging import add_breakpoint

      add_breakpoint(core, core.registers.ip.value + 4, ephemeral = True)

      core.wake_up()

    else:
      core.step()
      core.check_for_events()

      log_cpu_core_state(core, logger = core.INFO)

  except CPUException as e:
    core.die(e)

def cmd_core_state(console, cmd):
  """
  Print core state
  """

  M = console.master.machine
  core = console.default_core if console.default_core is not None else M.cpus[0].cores[0]

  do_log_cpu_core_state(core, logger = functools.partial(console.log, core.INFO))

def cmd_bt(console, cmd):
  """
  Print current backtrace
  """

  M = console.master.machine
  core = console.default_core if console.default_core is not None else M.cpus[0].cores[0]

  table = [
    ['Index', 'symbol', 'offset', 'ip']
  ]

  for index, (ip, symbol, offset) in enumerate(core.backtrace()):
    table.append([index, symbol, UINT32_FMT(offset), UINT32_FMT(ip)])

  console.table(table)
