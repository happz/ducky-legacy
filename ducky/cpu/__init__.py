import sys

from .. import console
from . import registers
from .. import mm
from .. import profiler

from ..interfaces import IMachineWorker, ISnapshotable
from ..mm import ADDR_FMT, UINT8_FMT, UINT16_FMT, UINT32_FMT, SEGMENT_SIZE, PAGE_SIZE, i16, UINT24_FMT
from .registers import Registers, REGISTER_NAMES
from .instructions import DuckyInstructionSet
from ..errors import AccessViolationError, InvalidResourceError
from ..util import debug, info, warn, error, print_table, LRUCache, exception
from ..snapshot import SnapshotNode

from ctypes import LittleEndianStructure, c_ubyte, c_ushort

#: Default size of core instruction cache, in instructions.
DEFAULT_CORE_INST_CACHE_SIZE = 256
#: Default size of core data cache, in words.
DEFAULT_CORE_DATA_CACHE_SIZE = 1024

class CPUState(SnapshotNode):
  pass

class CPUCoreState(SnapshotNode):
  def __init__(self):
    super(CPUCoreState, self).__init__('cpuid', 'coreid', 'registers', 'exit_code', 'alive', 'running', 'idle')

class InterruptVector(LittleEndianStructure):
  """
  Interrupt vector table entry.
  """

  _pack_ = 0
  _fields_ = [
    ('cs', c_ubyte),
    ('ds', c_ubyte),
    ('ip', c_ushort)
  ]

class CPUException(Exception):
  """
  Base class for CPU-related exceptions.

  :param string msg: message describing exceptional state.
  :param ducky.cpu.CPUCore core: CPU core that raised exception, if any.
  :param u16 ip: address of an instruction that caused exception, if any.
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

def do_log_cpu_core_state(core, logger = None):
  """
  Log state of a CPU core. Content of its registers, and other interesting or
  useful internal variables are logged.

  :param ducky.cpu.CPUCore core: core whose state should be logged.
  :param logger: called for each line of output to actualy log it. By default,
    core's :py:meth:`ducky.cpu.CPUCore.DEBUG` method is used.
  """

  logger = logger or core.DEBUG

  for i in range(0, Registers.REGISTER_SPECIAL, 4):
    regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
    s = ['reg{:02d}={}'.format(reg, UINT16_FMT(core.registers.map[reg].value)) for reg in regs]
    logger(' '.join(s))

  logger('cs=%s    ds=%s', UINT16_FMT(core.registers.cs.value), UINT16_FMT(core.registers.ds.value))
  logger('fp=%s    sp=%s    ip=%s', UINT16_FMT(core.registers.fp.value), UINT16_FMT(core.registers.sp.value), UINT16_FMT(core.registers.ip.value))
  logger('priv=%i, hwint=%i, e=%i, z=%i, o=%i, s=%i', core.registers.flags.privileged, core.registers.flags.hwint, core.registers.flags.e, core.registers.flags.z, core.registers.flags.o, core.registers.flags.s)
  logger('cnt=%s, idle=%s, exit=%i', core.registers.cnt.value, core.idle, core.exit_code)

  if hasattr(core, 'math_coprocessor'):
    for index, v in enumerate(core.math_coprocessor.registers.stack):
      logger('MS: %02i: %s', index, UINT32_FMT(v.value))

  if core.current_instruction:
    inst = core.instruction_set.disassemble_instruction(core.current_instruction)
    logger('current=%s', inst)
  else:
    logger('current=<none>')

  for index, (ip, symbol, offset) in enumerate(core.backtrace()):
    logger('Frame #%i: %s + %s (%s)', index, symbol, offset, ip)

def log_cpu_core_state(*args, **kwargs):
  """
  This is a wrapper for ducky.cpu.do_log_cpu_core_state function. Its main
  purpose is to be removed when debug mode is not set, therefore all debug
  calls of ducky.cpu.do_log_cpu_core_state will disappear from code,
  making such code effectively "quiet".
  """

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
    return '<StackFrame: CS={} DS={} FP={} IP={}, ({})'.format(UINT8_FMT(self.CS), UINT8_FMT(self.DS), UINT16_FMT(self.FP), UINT16_FMT(self.IP if self.IP is not None else 0), ADDR_FMT(self.address))

class InstructionCache(LRUCache):
  """
  Simple instruction cache class, based on LRU dictionary, with a limited size.

  :param ducky.cpu.CPUCore core: CPU core that owns this cache.
  :param int size: maximal number of entries this cache can store.
  """

  def __init__(self, core, size, *args, **kwargs):
    super(InstructionCache, self).__init__(size, *args, **kwargs)

    self.core = core

  def get_object(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param u24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

    return self.core.instruction_set.decode_instruction(self.core.memory.read_u32(addr, not_execute = False))

class CPUDataCache(LRUCache):
  """
  Simple data cache class, based on LRU dictionary, with a limited size.
  Operates on words, and only write-back policy is supported.

  All modified entries are marked as dirty, and are NOT written back to
  memory until cache is flushed or there is a need for space and entry is
  to be removed from cache.

  Helper methods are provided, to wrap cache API to a standardized "memory
  access" API. In the future, I may extend support to more sizes, or
  restructure internal storage to keep longer blocks keyed by address (like the
  real caches do). Therefore, CPU (and others) are expected to access data
  using :py:meth:`ducky.cpu.DataCache.read_u16` and
  :py:meth:`ducky.cpu.DataCache.write_u16`, instead of accessing raw values
  using address as a dictionary key.

  :param ducky.cpu.CPUCore core: CPU core that owns this cache.
  :param int size: maximal number of entries this cache can store.
  """

  def __init__(self, controller, core, size, *args, **kwargs):
    super(CPUDataCache, self).__init__(size, *args, **kwargs)

    self.controller = controller
    self.core = core

  def make_space(self):
    """
    Removes at least one of entries in cache, saving its content into memory
    when necessary.
    """

    addr, value = self.popitem(last = False)
    dirty, value = value

    self.core.DEBUG('CPUDataCache.make_space: addr=%s, value=%s', ADDR_FMT(addr), UINT16_FMT(value))

    if dirty:
      self.core.memory.write_u16(addr, value)

    self.prunes += 1

  def get_object(self, addr):
    """
    Read word from memory. This method is responsible for the real job of
    fetching data and filling the cache.

    :param u24 addr: absolute address to read from.
    :rtype: u16
    """

    self.core.DEBUG('CPUDataCache.get_object: address=%s', ADDR_FMT(addr))

    return [False, self.core.memory.read_u16(addr)]

  def read_u16(self, addr):
    """
    Read word from cache. Value is read from memory if it is not yet present
    in cache.

    :param u24 addr: absolute address to read from.
    :rtype: u16
    """

    self.core.DEBUG('CPUDataCache.read_u16: addr=%s', ADDR_FMT(addr))

    return self[addr][1]

  def write_u16(self, addr, value):
    """
    Write word to cache. Value in cache is overwritten, and marked as dirty. It
    is not written back to the memory yet.

    :param u24 addr: absolute address to modify.
    :param u16 value: new value to write.
    """

    self.core.DEBUG('CPUDataCache.write_u16: addr=%s, value=%s', ADDR_FMT(addr), UINT16_FMT(value))

    if addr not in self:
      self.__missing__(addr)

    self[addr] = [True, value]

    self.controller.release_entry_references(self.core, addr)

  def release_entry_references(self, addr, writeback = True, remove = True):
    """
    Remove entry that is located at specific address.

    :param u24 address: entry address
    :param bool writeback: if ``True``, value is written back to memory
      before it's removed from cache, otherwise it's just dropped.
    """

    self.core.DEBUG('CPUDataCache.release_entry_references: address=%s, writeback=%s, remove=%s', ADDR_FMT(addr), writeback, remove)

    dirty, value = self.get(addr, (None, None))

    if dirty is None and value is None:
      self.core.DEBUG('CPUDataCache.release_entry_references: not cached')
      return

    if dirty and writeback:
      self.core.memory.write_u16(addr, value)
      self.core.DEBUG('CPUDataCache.release_entry_references: written back')

    if remove:
      del self[addr]
      self.core.DEBUG('CPUDataCache.release_entry_references: removed')

    else:
      self[addr] = (False, value)

  def release_page_references(self, page, writeback = True, remove = True):
    """
    Remove entries that are located on a specific memory page.

    :param ducky.mm.MemoryPage page: referenced page.
    :param bool writeback: is ``True``, values are written back to memory
      before they are removed from cache, otherwise they are just dropped.
    """

    self.core.DEBUG('data_cache.release_page_references: page=%s, writeback=%s, remove=%s', page.index, writeback, remove)

    addresses = [i for i in range(page.base_address, page.base_address + PAGE_SIZE, 2)]

    for addr in self.keys():
      if addr not in addresses:
        continue

      self.release_entry_references(addr, writeback = writeback, remove = remove)

  def release_area_references(self, address, size, writeback = True, remove = True):
    self.core.DEBUG('CPUDataCache.remove_area_references: address=%s, size=%s, writeback=%s, remove=%s', ADDR_FMT(address), UINT16_FMT(size), writeback, remove)

    addresses = [i for i in range(address, address + size, 2)]

    for addr in self.keys():
      if addr not in addresses:
        continue

      self.release_entry_references(addr, writeback = writeback, remove = remove)

  def release_references(self, writeback = True, remove = True):
    """
    Save all dirty entries back to memory.
    """

    self.core.DEBUG('CPUDataCache.release_references: writeback=%s, remove=%s', writeback, remove)

    for addr in self.keys():
      self.release_entry_references(addr, writeback = writeback, remove = remove)

class CPUCacheController(object):
  def __init__(self):
    self.cores = []

  def register_core(self, core):
    self.cores.append(core)

  def unregister_core(self, core):
    self.cores.remove(core)

  def release_entry_references(self, caller, address):
    debug('CPUCacheController.release_entry_references: caller=%s, addresss=%s', str(caller), ADDR_FMT(address))

    writeback = True if caller is None else False
    map(lambda core: core.data_cache.release_entry_references(address, writeback = writeback, remove = True), [core for core in self.cores if core is not caller])

  def release_page_references(self, caller, pg):
    debug('CPUCacheController.release_page_references: caller=%s, pg=%s', str(caller), pg)

    writeback = True if caller is None else False
    map(lambda core: core.data_cache.release_page_references(pg, writeback = writeback, remove = True), [core for core in self.cores if core is not caller])

  def release_area_references(self, caller, address, size):
    debug('CPUCacheController.release_area_references: caller=%s, address=%s, size=%s', str(caller), ADDR_FMT(address), UINT24_FMT(size))

    writeback = True if caller is None else False
    map(lambda core: core.data_cache.release_area_references(address, size, writeback = writeback, remove = True), [core for core in self.cores if core is not caller])

  def release_references(self, caller):
    debug('CPUCacheController.release_references: caller=%s', str(caller))

    writeback = True if caller is None else False
    map(lambda core: core.data_cache.release_references(writeback = writeback, remove = True), [core for core in self.cores if core is not caller])

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

  def __init__(self, coreid, cpu, memory_controller, cache_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#{}:#{}: '.format(cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.registers = registers.RegisterSet()

    self.instruction_set = DuckyInstructionSet

    self.current_ip = None
    self.current_instruction = None

    self.alive = False
    self.running = False
    self.idle = False

    self.core_profiler = profiler.STORE.get_core_profiler(self)

    self.exit_code = 0

    self.frames = []
    self.check_frames = cpu.machine.config.getbool('cpu', 'check-frames', default = False)

    from .. import debugging
    self.debug = debugging.DebuggingSet(self)

    self.cache_controller = cache_controller
    self.instruction_cache = InstructionCache(self, self.cpu.machine.config.getint('cpu', 'inst-cache', default = DEFAULT_CORE_INST_CACHE_SIZE))
    self.data_cache = CPUDataCache(cache_controller, self, self.cpu.machine.config.getint('cpu', 'data-cache', default = DEFAULT_CORE_DATA_CACHE_SIZE))
    self.cache_controller.register_core(self)

    if self.cpu.machine.config.getbool('cpu', 'math-coprocessor', False):
      from .coprocessor import math_copro

      self.math_coprocessor = math_copro.MathCoprocessor(self)

  def has_coprocessor(self, name):
    return hasattr(self, '{}_coprocessor'.format(name))

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
    return '#{}:#{}'.format(self.cpu.id, self.id)

  def save_state(self, parent):
    self.DEBUG('core.save_state: parent=%s', parent)

    state = parent.add_child('core{}'.format(self.id), CPUCoreState())

    state.cpuid = self.cpu.id
    state.coreid = self.id

    state.registers = []

    for i, reg in enumerate(REGISTER_NAMES):
      if reg == 'flags':
        value = int(self.registers.flags.to_uint16())

      else:
        value = int(self.registers.map[reg].value)

      state.registers.append(value)

    state.exit_code = self.exit_code
    state.idle = self.idle
    state.alive = self.alive
    state.running = self.running

    if self.has_coprocessor('math'):
      self.math_coprocessor.save_state(state)

  def load_state(self, state):
    for i, reg in enumerate(REGISTER_NAMES):
      if reg == 'flags':
        self.registers.flags.from_uint16(state.registers[i])

      else:
        self.registers.map[reg].value = state.registers[i]

    self.exit_code = state.exit_code
    self.idle = state.idle
    self.alive = state.alive
    self.running = state.running

    if self.has_coprocessor('math'):
      self.math_coprocessor.load_state(state.get_children()['math_coprocessor'])

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

    :param u16 new_ip: new ``IP`` value, defaults to zero
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

    self.DEBUG('symbol_for_ip: %s%s (%s)', symbol, ' + {}'.format(offset if offset != 0 else ''), ip.value)

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

  def raw_push(self, val):
    """
    Push value on stack. ``SP`` is decremented by two, and value is written at this new address.

    :param u16 val: value to be pushed
    """

    self.registers.sp.value -= 2
    self.data_cache.write_u16(self.DS_ADDR(self.registers.sp.value), val)

  def raw_pop(self):
    """
    Pop value from stack. 2 byte number is read from address in ``SP``, then ``SP`` is incremented by two.

    :return: popped value
    :rtype: ``u16``
    """

    ret = self.data_cache.read_u16(self.DS_ADDR(self.registers.sp.value))
    self.registers.sp.value += 2
    return ret

  def push(self, *regs):
    for reg_id in regs:
      reg = self.registers.map[reg_id]

      self.DEBUG('push: %s (%s) at %s', reg_id, reg, UINT16_FMT(self.registers.sp.value - 2))
      value = self.registers.flags.to_uint16() if reg_id == Registers.FLAGS else self.registers.map[reg_id].value
      self.raw_push(value)

  def pop(self, *regs):
    for reg_id in regs:
      if reg_id == Registers.FLAGS:
        self.registers.flags.from_uint16(self.raw_pop())
      else:
        self.registers.map[reg_id].value = self.raw_pop()

      self.DEBUG('pop: %s (%s) from %s', reg_id, self.registers.map[reg_id], UINT16_FMT(self.registers.sp.value - 2))

  def create_frame(self):
    """
    Create new call stack frame. Push ``IP`` and ``FP`` registers and set ``FP`` value to ``SP``.
    """

    self.DEBUG('create_frame')

    self.push(Registers.IP, Registers.FP)

    self.registers.fp.value = self.registers.sp.value

    if self.check_frames:
      self.frames.append(StackFrame(self.registers.cs.value, self.registers.ds.value, self.registers.fp.value))

  def destroy_frame(self):
    """
    Destroy current call frame. Pop ``FP`` and ``IP`` from stack, by popping ``FP`` restores previous frame.

    :raises CPUException: if current frame does not match last created frame.
    """

    self.DEBUG('destroy_frame')

    if self.check_frames:
      if self.frames[-1].FP != self.registers.sp.value:
        raise CPUException('Leaving frame with wrong SP: IP={}, saved SP={}, current SP={}'.format(ADDR_FMT(self.registers.ip.value), ADDR_FMT(self.frames[-1].FP), ADDR_FMT(self.registers.sp.value)))

      self.frames.pop()

    self.pop(Registers.FP, Registers.IP)

    self.__symbol_for_ip()

  def __enter_interrupt(self, table_address, index):
    """
    Prepare CPU for handling interrupt routine. New stack is allocated, content fo registers
    is saved onto this new stack, and new call frame is created on this stack. CPU is switched
    into privileged mode. ``CS`` and ``IP`` are set to values, stored in interrupt descriptor
    table at specified offset.

    :param u24 table_address: address of interrupt descriptor table
    :param int index: interrupt number, its index into IDS
    """

    self.DEBUG('__enter_interrupt: table=%s, index=%i', table_address, index)

    iv = self.memory.load_interrupt_vector(table_address, index)

    stack_pg, sp = self.memory.alloc_stack(segment = iv.ds)

    old_SP = self.registers.sp.value
    old_DS = self.registers.ds.value

    self.registers.ds.value = iv.ds
    self.registers.sp.value = sp

    self.raw_push(old_DS)
    self.raw_push(old_SP)
    self.push(Registers.CS, Registers.FLAGS)
    self.push(*[i for i in range(0, Registers.REGISTER_SPECIAL)])
    self.create_frame()

    self.privileged = 1

    self.registers.cs.value = iv.cs
    self.registers.ip.value = iv.ip

    if self.check_frames:
      self.frames[-1].IP = iv.ip

  def exit_interrupt(self):
    """
    Restore CPU state after running a interrupt routine. Call frame is destroyed, registers
    are restored, stack is returned back to memory pool.
    """

    self.DEBUG('exit_interrupt')

    self.destroy_frame()
    self.pop(*[i for i in reversed(range(0, Registers.REGISTER_SPECIAL))])
    self.pop(Registers.FLAGS, Registers.CS)

    stack_page = self.memory.get_page(mm.addr_to_page(self.DS_ADDR(self.registers.sp.value)))

    old_SP = self.raw_pop()
    old_DS = self.raw_pop()

    self.registers.ds.value = old_DS
    self.registers.sp.value = old_SP

    self.data_cache.release_page_references(stack_page, writeback = False)
    self.memory.free_page(stack_page)

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
      self.__enter_interrupt(self.memory.int_table_address, index)

      self.DEBUG('do_int: CPU state prepared to handle interrupt')

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

  def check_protected_ins(self):
    """
    Raise ``AccessViolationError`` if core is not running in privileged mode.

    This method should be used by instruction handlers that require privileged mode, e.g. protected instructions.

    :raises AccessViolationError: if the core is not in privileged mode
    """

    if not self.privileged:
      raise AccessViolationError('Instruction not allowed in unprivileged mode: opcode={}'.format(self.current_instruction.opcode))

  def check_protected_reg(self, *regs):
    for reg in regs:
      if reg in registers.PROTECTED_REGISTERS and not self.privileged:
        raise AccessViolationError('Access not allowed in unprivileged mode: opcode={}, reg={}'.format(self.current_instruction.opcode, reg))

  def check_protected_port(self, port):
    if port not in self.cpu.machine.ports:
      raise InvalidResourceError('Unhandled port: port={}'.format(port))

    if self.cpu.machine.ports[port].is_protected and not self.privileged:
      raise AccessViolationError('Access to port not allowed in unprivileged mode: opcode={}, port={}'.format(self.current_instruction.opcode, port))

  def update_arith_flags(self, *regs):
    """
    Set relevant arithmetic flags according to content of registers. Flags are set to zero at the beginning,
    then content of each register is examined, and ``S`` and ``Z`` flags are set.

    ``E`` flag is not touched, ``O`` flag is set to zero.

    :param list regs: list of ``u16`` registers
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

    :param u16 x: left hand number
    :param u16 y: right hand number
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

    self.DEBUG('"EXECUTE" phase: %s %s', UINT16_FMT(self.current_ip), self.instruction_set.disassemble_instruction(self.current_instruction))
    log_cpu_core_state(self)

    try:
      if opcode not in self.instruction_set.opcode_desc_map:
        raise InvalidOpcodeError(opcode, ip = self.current_ip, core = self)

      self.instruction_set.opcode_desc_map[opcode].execute(self, self.current_instruction)

    except (InvalidOpcodeError, AccessViolationError, InvalidResourceError) as e:
      self.die(e)
      return

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

    self.data_cache.release_references(writeback = True, remove = False)

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

    except Exception as e:
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

    self.core_profiler.enable()

    self.INFO('Booted')

class CPU(ISnapshotable, IMachineWorker):
  def __init__(self, machine, cpuid, memory_controller, cache_controller, cores = 1):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#{}:'.format(cpuid)

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller
    self.cache_controller = cache_controller

    self.cores = []
    for i in xrange(0, cores):
      __core = CPUCore(i, self, self.memory, self.cache_controller)
      self.cores.append(__core)

  def save_state(self, parent):
    state = parent.add_child('cpu{}'.format(self.id), CPUState())

    map(lambda __core: __core.save_state(state), self.cores)

  def load_state(self, state):
    for core_state in state.get_children().itervalues():
      self.cores[core_state.coreid].load_state(core_state)

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
    inst = core.instruction_set.decode_instruction(core.memory.read_u32(__ip_addr()))

    if inst.opcode == core.instruction_set.opcodes.CALL:
      from ..debugging import add_breakpoint

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
