import functools
import sys

from six import iterkeys, itervalues, iteritems
from six.moves import range

from functools import partial

from . import registers
from .. import profiler

from ..interfaces import IMachineWorker, ISnapshotable
from ..mm import UINT8_FMT, UINT16_FMT, UINT32_FMT, PAGE_SIZE, PAGE_MASK, PAGE_SHIFT, PageTableEntry, UINT64_FMT, WORD_SIZE
from .registers import Registers, REGISTER_NAMES
from .instructions import DuckyInstructionSet, EncodingContext
from ..errors import ExceptionList, AccessViolationError, InvalidResourceError, ExecutionException, InvalidOpcodeError, MemoryAccessError, InvalidExceptionError, PrivilegedInstructionError, InvalidFrameError, UnalignedAccessError
from ..util import LoggingCapable, Flags
from ..snapshot import SnapshotNode

#: Default EVT address
DEFAULT_EVT_ADDRESS = 0x00000000

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
    super(CPUCoreState, self).__init__('cpuid', 'coreid', 'registers', 'exit_code', 'alive', 'running', 'idle', 'evt_address', 'pt_address', 'pt_enabled', 'flags')

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

  @staticmethod
  def load(core, addr):
    core.DEBUG('InterruptVector.load: addr=%s', UINT32_FMT(addr))

    desc = InterruptVector()
    desc.ip = core.MEM_IN32(addr)
    desc.sp = core.MEM_IN32(addr + WORD_SIZE)

    return desc

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
    s = ['r{:02d}={}'.format(reg, UINT32_FMT(core.registers[reg])) for reg in regs]
    logger(' '.join(s))

  logger(' fp=%s  sp=%s  ip=%s', UINT32_FMT(core.registers[Registers.FP]), UINT32_FMT(core.registers[Registers.SP]), UINT32_FMT(core.registers[Registers.IP]))
  logger('flags=%s', core.flags.to_string())
  logger('cnt=%s, alive=%s, running=%s, idle=%s, exit=%i', core.registers[Registers.CNT], core.alive, core.running, core.idle, core.exit_code)

  if hasattr(core, 'math_coprocessor'):
    for index, v in enumerate(core.math_coprocessor.registers.stack):
      logger('MC: %02i: %s', index, UINT64_FMT(v.value))

  if hasattr(core, 'control_coprocessor'):
    cp = core.control_coprocessor
    logger('CC: cr0=%s, cr1=%s, cr2=%s, cr3=%s', UINT32_FMT(cp.read_cr0()), UINT32_FMT(cp.read_cr1()), UINT32_FMT(cp.read_cr2()), UINT32_FMT(cp.read_cr3()))

  if disassemble is True:
    if core.current_instruction is not None:
      inst = inst_set.disassemble_instruction(core.LOGGER, core.current_instruction)
    else:
      inst = '<none>'
  else:
    inst = '<unknown>'

  logger('current-inst: inst-set=%02d ip=%s inst=%s', inst_set.instruction_set_id, UINT32_FMT(core.current_ip) if core.current_ip is not None else '<unknown>', inst)

  for index, frame in enumerate(core.frames):
    logger('Frame #%i: %s %s', index, UINT32_FMT(frame.sp), UINT32_FMT(frame.ip))

def log_cpu_core_state(*args, **kwargs):
  """
  This is a wrapper for ducky.cpu.do_log_cpu_core_state function. Its main
  purpose is to be removed when debug mode is not set, therefore all debug
  calls of ducky.cpu.do_log_cpu_core_state will disappear from code,
  making such code effectively "quiet".
  """

  do_log_cpu_core_state(*args, **kwargs)

class StackFrame(object):
  def __init__(self, sp, ip):
    super(StackFrame, self).__init__()

    self.sp = sp
    self.ip = ip

  def __getattribute__(self, name):
    if name == 'address':
      return self.sp

    return super(StackFrame, self).__getattribute__(name)

  def __repr__(self):
    return '<StackFrame: SP={}, IP={}>'.format(UINT32_FMT(self.sp), UINT32_FMT(self.ip))


class CoreFlags(Flags):
  _flags = ['privileged', 'hwint_allowed', 'equal', 'zero', 'overflow', 'sign']
  _labels = 'PHEZOS'

class InstructionCache_Base(LoggingCapable, dict):
  """
  Simple instruction cache class, based on a dictionary, with a limited size.

  :param ducky.cpu.CPUCore core: CPU core that owns this cache.
  """

  def __init__(self, mmu, *args, **kwargs):
    super(InstructionCache_Base, self).__init__(mmu.core.cpu.machine.LOGGER)

    self._mmu = mmu
    self._core = mmu.core

  def __getitem__(self, addr):
    """
    Get instruction from the specified address.
    """

    index = addr >> 2

    i = dict.get(self, index)

    if i is None:
        i = self.fetch_instr(addr)
        dict.__setitem__(self, index, i)

    return i

class InstructionCache_Full(LoggingCapable, list):
  """
  Simple instruction cache class, based on a list, with unlimited size.

  :param ducky.cpu.CPUCore core: CPU core that owns this cache.
  """

  def __init__(self, mmu, *args, **kwargs):
    super(InstructionCache_Full, self).__init__(mmu.core.cpu.machine.LOGGER, [None for _ in range(0, mmu.memory.size >> 2)])

    self._mmu = mmu
    self._core = mmu.core

    self.reads   = 0
    self.hits    = 0
    self.misses  = 0

  def clear(self):
    for i in range(0, self._mmu.memory.size >> 2):
      self[i] = None

  def __getitem__(self, addr):
    """
    Get instruction from the specified address.
    """

    self.reads += 1

    index = addr >> 2

    i = list.__getitem__(self, index)

    if i is None:
        self.misses += 1

        i = self.fetch_instr(addr)
        list.__setitem__(self, index, i)

    else:
      self.hits += 1

    return i

class MMU(ISnapshotable):
  """
  Memory management unit (aka MMU) provides a single point handling all core's memory operations.
  All memory reads and writes must go through this unit, which is then responsible for all
  translations, access control, and caching.

  :param ducky.cpu.CPUCore core: parent core.
  :param ducky.mm.MemoryController memory_controller: memory controller that
    provides access to the main memory.
  :param bool memory.force-aligned-access: if set, MMU will disallow unaligned
    reads and writes. ``False`` by default.
  :param int cpu.pt-address: base address of page table.
    :py:const:`ducky.cpu.DEFAULT_PT_ADDRESS` by default.
  :param bool cpu.pt-enabled: if set, CPU core will start with page table
    enabled. ``False`` by default.
  """

  def __init__(self, core, memory_controller):
    super(MMU, self).__init__()

    config = core.cpu.machine.config

    self.core = core
    self.memory = memory_controller

    self.force_aligned_access = config.memory_force_aligned_access()
    self.pt_address = config.cpu_pt_address()
    self._pt_enabled = config.cpu_pt_enabled()

    self._pte_cache = {}

    self.DEBUG = core.DEBUG

    if config.cpu_instr_cache() == 'full':
      self._instruction_cache = InstructionCache_Full(self)

    else:
      self._instruction_cache = InstructionCache_Base(self)

    if config.cpu_page_cache() == 'full':
      self._page_cache = [None for _ in range(0, self.memory.pages_cnt)]

    else:
      self._page_cache = dict()

    self._set_access_methods()

  def _get_pt_enabled(self):
    return self._pt_enabled

  def _set_pt_enabled(self, value):
    self._pt_enabled = value

    self._set_access_methods()

  pt_enabled = property(_get_pt_enabled, _set_pt_enabled)

  def _debug_wrapper_read(self, reader, *args, **kwargs):
    self.core.debug.pre_memory(args[0], read = True)

    if not self.core.running:
      return

    value = reader(*args, **kwargs)

    self.core.debug.post_memory(args[0], read = True)

    return value

  def _debug_wrapper_write(self, writer, *args, **kwargs):
    self.core.debug.pre_memory(args[0], read = False)

    if not self.core.running:
      return

    writer(*args, **kwargs)

    self.core.debug.post_memory(args[0], read = False)

  def _set_access_methods(self):
    """
    Set parent core's memory-access methods to proper shortcuts. Methods named
    ``MEM_{IN,OUT}{8,16,32}`` will be set to corresponding MMU methods.
    """

    self.DEBUG('MMU._set_access_methods')

    def __set_methods(set_name):
      self.core.MEM_IN8   = getattr(self, '_' + set_name + '_read_u8')
      self.core.MEM_IN16  = getattr(self, '_' + set_name + '_read_u16')
      self.core.MEM_IN32  = getattr(self, '_' + set_name + '_read_u32')
      self.core.MEM_OUT8  = getattr(self, '_' + set_name + '_write_u8')
      self.core.MEM_OUT16 = getattr(self, '_' + set_name + '_write_u16')
      self.core.MEM_OUT32 = getattr(self, '_' + set_name + '_write_u32')

    def __wrap_debug():
      self.core.MEM_IN8   = partial(self._debug_wrapper_read,  self.core.MEM_IN8)
      self.core.MEM_IN16  = partial(self._debug_wrapper_read,  self.core.MEM_IN16)
      self.core.MEM_IN32  = partial(self._debug_wrapper_read,  self.core.MEM_IN32)
      self.core.MEM_OUT8  = partial(self._debug_wrapper_write, self.core.MEM_OUT8)
      self.core.MEM_OUT16 = partial(self._debug_wrapper_write, self.core.MEM_OUT16)
      self.core.MEM_OUT32 = partial(self._debug_wrapper_write, self.core.MEM_OUT32)

    if self._pt_enabled is True:
      __set_methods('pt')

    else:
      __set_methods('nopt')

    if self.core.debug is not None:
      __wrap_debug()

    self._instruction_cache.fetch_instr = self._fetch_instr_jit if self.core.jit is True else self._fetch_instr
    self._get_pg_ops = self._get_pg_ops_list if self.core.cpu.machine.config.get('cpu', 'page-cache', 'simple') == 'full' else self._get_pg_ops_dict
    self.core.fetch_instr = self._instruction_cache.__getitem__

  def reset(self):
    """
    Reset MMU. PT will be disabled, and all internal caches will be flushed.
    """

    self._instruction_cache.clear()

    if isinstance(self._page_cache, list):
      for i in range(0, self.memory.pages_cnt):
        self._page_cache[i] = None
    else:
      self._page_cache.clear()

    self.pt_enabled = False
    self._pte_cache = {}

  def halt(self):
    pass

  def release_ptes(self):
    """
    Clear internal PTE cache.
    """

    self.DEBUG('%s.release_ptes', self.__class__.__name__)

    self._pte_cache = {}

  def _get_pte(self, addr):
    """
    Find out PTE for particular physical address. If PTE is not in internal PTE cache, it is
    fetched from PTE table.

    :param int addr: memory address.
    """

    pg_index = (addr & PAGE_MASK) >> PAGE_SHIFT
    pte_address = self.pt_address + pg_index

    self.DEBUG('%s._get_pte: addr=%s, pg=%s, pte-address=%s', self.__class__.__name__, UINT32_FMT(addr), pg_index, UINT32_FMT(pte_address))

    if pg_index not in self._pte_cache:
      self._pte_cache[pg_index] = pte = PageTableEntry.from_int(self.memory.read_u8(pte_address))

    else:
      pte = self._pte_cache[pg_index]

    self.DEBUG('%s._get_pte: pte=%s,%s', pte.to_string(), pte.to_int())

    return pte

  def _check_access(self, access, addr, align = None):
    """
    Check attempted access against several criteria:

     - PT is enabled - disabled PT implies different set of read/write methods
       that don't use this method to check access
     - access alignment if correct alignment is required
     - privileged access implies granted access
     - corresponding PTE settings

    :param access: ``read``, ``write`` or ``execute``.
    :param int addr: memory address.
    :param int align: if set, operation is expected to be aligned to this boundary.
    :raises ducky.errors.UnalignedAccessError: when unaligned access is not
      allowed, but requested.
    :raises ducky.errors.MemoryAccessError: when access is denied.
    """

    self.DEBUG('%s._check_access: access=%s, addr=%s, align=%s', self.__class__.__name__, access, UINT32_FMT(addr), align)

    if self.force_aligned_access is True and align is not None and addr % align:
      raise UnalignedAccessError(core = self.core)

    pg_index = (addr & PAGE_MASK) >> PAGE_SHIFT

    if self.core.privileged is True:
      return self.memory.get_page(pg_index)

    pte = self._get_pte(addr)

    if getattr(pte, access) is True:
      return self.memory.get_page(pg_index)

    raise MemoryAccessError(access, addr, pte)

  def _get_pg_ops_list(self, address):
    pg_index = address >> PAGE_SHIFT
    pg_cache = self._page_cache

    ops = pg_cache[pg_index]
    if ops is not None:
      return ops

    pg = self.memory.get_page(pg_index)
    pg_cache[pg_index] = ops = (pg.read_u8, pg.read_u16, pg.read_u32, pg.write_u8, pg.write_u16, pg.write_u32)

    return ops

  def _get_pg_ops_dict(self, address):
    pg_index = address >> PAGE_SHIFT
    pg_cache = self._page_cache

    if pg_index in pg_cache:
      return pg_cache[pg_index]

    pg = self.memory.get_page(pg_index)
    pg_cache[pg_index] = ops = (pg.read_u8, pg.read_u16, pg.read_u32, pg.write_u8, pg.write_u16, pg.write_u32)

    return ops

  def _fetch_instr(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param u24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

    core = self.core

    inst, desc, opcode = core.decode_instr(core.MEM_IN32(addr, not_execute = False))
    return inst, opcode, partial(desc.execute, core, inst)

  def _fetch_instr_jit(self, addr):
    """
    Read instruction from memory. This method is responsible for the real job of
    fetching instructions and filling the cache.

    :param u24 addr: absolute address to read from
    :return: instruction
    :rtype: ``InstBinaryFormat_Master``
    """

    core = self.core

    inst, desc, opcode = core.decode_instr(core.MEM_IN32(addr, not_execute = False))

    fn = desc.jit(core, inst)

    if fn is None:
      return inst, opcode, partial(desc.execute, core, inst)

    return inst, opcode, fn

  # "PT Disabled" methods - every access is effectively privileged
  def _nopt_read_u8(self, addr):
    self.DEBUG('MMU._nopt_read_u8: addr=%s', UINT32_FMT(addr))

    return self._get_pg_ops(addr)[0](addr & ~PAGE_MASK)

  def _nopt_read_u16(self, addr):
    self.DEBUG('MMU._nopt_read_u16: addr=%s', UINT32_FMT(addr))

    return self._get_pg_ops(addr)[1](addr & ~PAGE_MASK)

  def _nopt_read_u32(self, addr, not_execute = True):
    self.DEBUG('MMU._nopt_read_u32: addr=%s', UINT32_FMT(addr))

    return self._get_pg_ops(addr)[2](addr & ~PAGE_MASK)

  def _nopt_write_u8(self, addr, value):
    self.DEBUG('MMU._nopt_write_u8: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    return self._get_pg_ops(addr)[3](addr & ~PAGE_MASK, value)

  def _nopt_write_u16(self, addr, value):
    self.DEBUG('MMU._nopt_write_u16: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    return self._get_pg_ops(addr)[4](addr & ~PAGE_MASK, value)

  def _nopt_write_u32(self, addr, value):
    self.DEBUG('MMU._nopt_write_u32: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    return self._get_pg_ops(addr)[5](addr & ~PAGE_MASK, value)

  # "PT Enabled" methods - checking access
  def _pt_read_u8(self, addr):
    self.DEBUG('MMU._pt_read_u8: addr=%s', UINT32_FMT(addr))

    return self._check_access('read', addr).read_u8(addr & (PAGE_SIZE - 1))

  def _pt_read_u16(self, addr):
    self.DEBUG('MMU._pt_read_u16: addr=%s', UINT32_FMT(addr))

    return self._check_access('read', addr, align = 2).read_u16(addr & (PAGE_SIZE - 1))

  def _pt_read_u32(self, addr, not_execute = True):
    self.DEBUG('MMU._pt_read_u32: addr=%s', UINT32_FMT(addr))

    pg = self._check_access('read', addr, align = 4)

    if not_execute is not True:
      pg = self._check_access('execute', addr)

    return pg.read_u32(addr & (PAGE_SIZE - 1))

  def _pt_write_u8(self, addr, value):
    self.DEBUG('MMU._pt_write_u8: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    return self._check_access('write', addr).write_u8(addr & (PAGE_SIZE - 1), value)

  def _pt_write_u16(self, addr, value):
    self.DEBUG('MMU._pt_write_u16: addr=%s, value=%s', UINT32_FMT(addr), UINT16_FMT(value))

    return self._check_access('write', addr).write_u16(addr & (PAGE_SIZE - 1), value)

  def _pt_write_u32(self, addr, value):
    self.DEBUG('MMU._pt_write_u32: addr=%s, value=%s', UINT32_FMT(addr), UINT32_FMT(value))

    return self._check_access('write', addr).write_u32(addr & (PAGE_SIZE - 1), value)

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

    config.memory_force_aligned_access = partial(config.getbool, 'memory', 'force-aligned-access', default = False)
    config.cpu_pt_address = partial(config.getint, 'cpu', 'pt-address', default = DEFAULT_PT_ADDRESS)
    config.cpu_pt_enabled = partial(config.getbool, 'cpu', 'pt-enabled', default = False)
    config.cpu_instr_cache = partial(config.get, 'cpu', 'instr-cache', default = 'simple')
    config.cpu_page_cache = partial(config.get, 'cpu', 'page-cache', default = 'simple')

    self.cpuid = '#{}:#{}'.format(cpu.id, coreid)
    self.cpuid_prefix = self.cpuid + ':'

    self.jit = config.getbool('machine', 'jit', default = False)
    self.check_frames = cpu.machine.config.getbool('cpu', 'check-frames', default = False)

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

    self.evt_address = config.getint('cpu', 'evt-address', DEFAULT_EVT_ADDRESS)

    self.encoding_context = EncodingContext(self.LOGGER)

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

    self.coprocessors = {}

    if self.cpu.machine.config.getbool('cpu', 'math-coprocessor', False):
      from .coprocessor import math_copro

      self.math_coprocessor = self.coprocessors['math'] = math_copro.MathCoprocessor(self)

    if config.getbool('cpu', 'control-coprocessor', True):
      from .coprocessor import control
      self.control_coprocessor = self.coprocessors['control'] = control.ControlCoprocessor(self)

  def _get_instruction_set(self):
    return self._instruction_set

  def _set_instruction_set(self, instr_set):
    self._instruction_set = instr_set
    self.decode_instr = partial(self.encoding_context.decode, instr_set, core = self)

  instruction_set = property(_get_instruction_set, _set_instruction_set)

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

    for i, reg_name in enumerate(REGISTER_NAMES):
      state.registers.append(self.registers[i])

    state.evt_address = self.evt_address
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
      self.registers[reg] = state.registers[i]

    self.evt_address = state.evt_address
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

      self.mmu._set_access_methods()

  def REG(self, reg):
    return self.registers[reg]

  def IP(self):
    return self.registers[Registers.IP]

  def SP(self):
    return self.registers[Registers.SP]

  def FP(self):
    return self.registers[Registers.FP]

  def reset(self, new_ip = 0x00000000):
    """
    Reset core's state. All registers are set to zero, all flags are set to zero,
    except ``HWINT`` flag which is set to one, and ``IP`` is set to requested value.

    :param u32_t new_ip: new ``IP`` value, defaults to zero
    """

    self.instruction_set = DuckyInstructionSet
    self.instruction_set_stack = []

    for reg in registers.RESETABLE_REGISTERS:
      self.registers[reg] = 0

    self.flags = CoreFlags.create(privileged = True)

    self.registers[Registers.IP] = new_ip
    self.current_ip = new_ip

    self.mmu.reset()

  def _handle_python_exception(self, exc):
    if isinstance(exc, ExecutionException):
      if exc.core is None:
        exc.core = self

      if exc.ip is None:
        exc.ip = self.current_ip

      if exc.runtime_handle() is not True:
        self.die(exc)
        return False

      return True

    if isinstance(exc, (AccessViolationError, InvalidResourceError)):
      self.die(exc)
      return False

    raise

  def _raw_push(self, val):
    """
    Push value on stack. ``SP`` is decremented by four, and value is written at this new address.

    :param u32 val: value to be pushed
    """

    self.DEBUG('_raw_push: sp=%s, addr=%s, value=%s', UINT32_FMT(self.registers[Registers.SP]), UINT32_FMT(self.registers[Registers.SP] - WORD_SIZE), UINT32_FMT(val))

    self.registers[Registers.SP] = (self.registers[Registers.SP] - 4) % 4294967296
    self.MEM_OUT32(self.registers[Registers.SP], val)

  def _raw_pop(self):
    """
    Pop value from stack. 4 byte number is read from address in ``SP``, then ``SP`` is incremented by four.

    :return: popped value
    :rtype: ``u32``
    """

    sp = self.registers[Registers.SP]

    self.DEBUG('_raw_pop: sp=%s', UINT32_FMT(sp))

    ret = self.MEM_IN32(sp)
    self.registers[Registers.SP] = (self.registers[Registers.SP] + WORD_SIZE) % 4294967296
    self.DEBUG('_raw_pop: value=%s', UINT32_FMT(ret))

    return ret

  def push(self, *regs):
    self.DEBUG('push: regs=%s', regs)

    for reg_id in regs:
      self._raw_push(self.registers[reg_id])

  def push_flags(self):
    self.DEBUG('push_flags')

    self._raw_push(self.flags.to_int())

  def pop(self, *regs):
    self.DEBUG('pop: regs=%s', regs)

    for reg_id in regs:
      self.registers[reg_id] = self._raw_pop()

  def pop_flags(self):
    self.DEBUG('pop_flags')

    self.flags = CoreFlags.from_int(self._raw_pop())

  def create_frame(self):
    """
    Creates new call stack frame, by performing the following operations:

      - push ``IP``
      - push ``FP``
      - set ``FP`` to ``SP`` (i.e. ``SP`` before this method + 2 pushes)

    Stack layout then looks like this::

        +---------+
        |   IPx   |
        +---------+
        |   FPx   |
        +---------+ <= FPy
        |   ...   |
        +---------+ <= original SP
        |   IPy   |
        +---------+
        |   FPy   |
        +---------+ <= SP, FP
        |   ...   |
        +---------+

    ``FP`` then points to the newly created frame, to the saved ``FP``
    in particular, and this saved ``FP`` points to its predecesor, thus
    forming a chain.
    """

    self.DEBUG('create_frame')

    self.push(Registers.IP, Registers.FP)
    self.registers[Registers.FP] = self.registers[Registers.SP]

    return StackFrame(self.registers[Registers.SP], self.current_ip) if self.jit is False else None

  def destroy_frame(self):
    """
    Destroys current call stack frame by popping values from the stack,
    reversing the list of operations performed by
    :py:meth:`ducky.cpu.CPUCore.create_frame`:

      - pop ``FP``
      - pop ``IP``

    After this, ``FP`` points to the frame from which the instruction that
    created the currently destroyed frame was executed, and restored ``IP``
    points to the next instruction.

    :raises InvalidFrameError: if frame checking is enabled, current ``SP``
      is compared with saved ``FP`` to see, if the stack was clean before
      leaving the frame. This error indicated there is some value left
      on stack when ``ret`` or ``retint`` were executed. Usually, this
      signals missing ``pop`` to complement one of previous ``push``es.
    """

    self.DEBUG('destroy_frame')

    self.pop(Registers.FP, Registers.IP)

  def pop_frame(self):
    frame = self.frames.pop(-1)

    if not self.check_frames:
      return

    if frame.sp != self.registers[Registers.SP]:
      raise InvalidFrameError(frame.sp, self.registers[Registers.SP])

  def _enter_exception(self, index, *args):
    """
    Prepare CPU for handling exception routine. CPU core loads new ``IP``
    and ``SP`` from proper entry of EVT. Old ``SP`` and ``FLAGS`` are saved
    on the exception stack, and new call frame is created. Privileged mode
    flag is set, hardware interrupt flag is cleared.

    Then, if exception provides its routine with some arguments, these
    arguments are pushed on the stack.

    Exception stack layout then looks like this (original stack is left
    untouched)::

        +---------+ <= EVT SP
        |   SP    |
        +---------+
        |  FLAGS  |
        +---------+
        |   IP    |
        +---------+
        |   FP    |
        +---------+ <= FP
        |   arg1  |
        +---------+
        |   ...   |
        +---------+
        |   argN  |
        +---------+ <= SP
        |   ...   |
        +---------+

    :param int index: exception ID - EVT index.
    :param u32_t args: if present, these values will be pushed onto the stack.
    """

    self.DEBUG('_enter_exception: index=%s', UINT8_FMT(index))

    if index >= ExceptionList.COUNT:
      raise InvalidExceptionError(index)

    iv = InterruptVector.load(self, self.evt_address + index * InterruptVector.SIZE)

    self.DEBUG('_enter_exception: desc=%s', iv)

    old_SP = self.registers[Registers.SP]

    self.registers[Registers.SP] = iv.sp

    self._raw_push(old_SP)
    self.push_flags()
    frame = self.create_frame()

    self.DEBUG('_enter_exception: pushing args')
    for arg in args:
      self._raw_push(arg)

    self.privileged = True
    self.hwint_allowed = False

    self.registers[Registers.IP] = iv.ip

    if frame is not None:
      frame.IP = iv.ip
      self.frames.append(frame)

    self.instruction_set_stack.append(self.instruction_set)
    self.instruction_set = DuckyInstructionSet

    log_cpu_core_state(self, inst_set = self.instruction_set_stack[-1])

  def _exit_exception(self):
    """
    Restore CPU state after running an exception routine. Call frame is
    destroyed, registers are restored. Clearing routine arguments is
    responsibility of the routine.
    """

    self.DEBUG('_exit_exception')

    self.destroy_frame()
    self.pop_flags()

    old_SP = self._raw_pop()

    self.registers[Registers.SP] = old_SP

    self.instruction_set = self.instruction_set_stack.pop(0)

  def _handle_exception(self, exc, index, *args):
    """
    This method provides CPU exception classes with a simple recipe on how
    to deal with the exception:

      - tell processor to start exception dance,
      - if the exception is raised again, tell processor to plan double fault
        routine,
      - and if yet another exception is raised, halt the core.
    """

    self.DEBUG('_handle_exception: exc=%r, index=%d, args=%s', exc, index, args)

    try:
      self._enter_exception(index, *args)

    except ExecutionException as e1:
      self.DEBUG('Exception raised when preparing to handle an exception => double fault')
      self.WARN(str(e1))

      try:
        self._enter_exception(ExceptionList.DoubleFault, index, *args)

      except ExecutionException as e2:
        self.die(e2)

  def irq(self, index):
    """
    This is a wrapper for _enter_exception, for device drivers to call
    when hardware interrupt arrives.

    :param int index: exception ID - EVT index
    """

    try:
      self._enter_exception(index)

    except Exception as exc:
      if self._handle_python_exception(exc) is not True:
        return

    self.change_runnable_state(idle = False)

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

    :raises ducky.errors.PrivilegedInstructionError: if the core is not in privileged mode
    """

    if not self.privileged:
      raise PrivilegedInstructionError(core = self)

  def do_step(self, ip, regset):
    self.current_instruction, opcode, execute = self.fetch_instr(ip)
    regset[Registers.IP] = (ip + 4) % 4294967296

    self.DEBUG('"EXECUTE" phase: %s %s', UINT32_FMT(ip), self.instruction_set.disassemble_instruction(self.LOGGER, self.current_instruction))
    log_cpu_core_state(self)

    execute()

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

    regset = self.registers
    ip = regset[Registers.IP]
    self.current_ip = ip

    self.DEBUG('fetch instruction: ip=%s', UINT32_FMT(ip))

    try:
      self.do_step(ip, regset)

    except Exception as exc:
      if self._handle_python_exception(exc) is not True:
        return

    regset[Registers.CNT] += 1

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
    self.cpu.machine.tenh('%r:  check-frames: %s', self, 'yes' if self.check_frames else 'no')
    self.cpu.machine.tenh('%r:  instruction cache: %s', self, self.cpu.machine.config.get('cpu', 'instr-cache', 'simple'))
    self.cpu.machine.tenh('%r:  page cache: %s', self, self.cpu.machine.config.get('cpu', 'page-cache', 'simple'))
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
