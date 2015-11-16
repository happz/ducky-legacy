"""
:py:class:`ducky.machine.Machine` is *the* virtual machine. Each instance
represents self-contained virtual machine, with all its devices, memory, CPUs
and other necessary properties.
"""

import itertools
import collections
import importlib
import os
import sys
import time

from ctypes import LittleEndianStructure, c_uint, c_ushort, sizeof
from functools import partial
from enum import IntEnum

from six import itervalues, iteritems

from . import mm
from . import snapshot
from . import util

from . import __version__

from .interfaces import IMachineWorker, ISnapshotable, IReactorTask

from .console import ConsoleMaster
from .errors import InvalidResourceError
from .log import create_logger
from .util import LRUCache, F, align, sizeof_fmt
from .mm import addr_to_segment, ADDR_FMT, segment_addr_to_addr, UInt8, UInt16, UInt32, UINT16_FMT, UINT32_FMT, PAGE_SIZE
from .mm.binary import SectionFlags
from .reactor import Reactor
from .snapshot import SnapshotNode

HDT_MAGIC = 0x4D5E

class HDTEntryTypes(IntEnum):
  CPU    = 0
  MEMORY = 1

class HDTStructure(LittleEndianStructure):
  _pack_ = 0

  def write(self, machine, address):
    write_u8  = partial(machine.memory.write_u8,  privileged = True)
    write_u16 = partial(machine.memory.write_u16, privileged = True)
    write_u32 = partial(machine.memory.write_u32, privileged = True)

    for n, t in self._fields_:
      if sizeof(t) == 1:
        write_u8(address, getattr(self, n))
        address += 1

      elif sizeof(t) == 2:
        write_u16(address, getattr(self, n))
        address += 2

      else:
        write_u32(address, getattr(self, n))
        address += 4

    return address

class HDTHeader(HDTStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',   c_ushort),
    ('entries', c_ushort)
  ]

  @staticmethod
  def create(machine):
    machine.DEBUG('HDTHeader.create')

    header = HDTHeader()

    header.magic = 0x4D5E
    header.entries = 0

    return header

class HDTEntry(HDTStructure):
  @classmethod
  def create(cls, entry_type):
    entry = cls()

    entry.type = entry_type
    entry.length = sizeof(cls)

    return entry

class HDTEntry_CPU(HDTEntry):
  _pack_ = 0
  _fields_ = [
    ('type',     c_ushort),
    ('length',   c_ushort),
    ('nr_cpus',  c_ushort),
    ('nr_cores', c_ushort)
  ]

  @classmethod
  def create(cls, machine):
    machine.DEBUG('HDTEntry_CPU.create: nr_cpus=%s, nr_cores=%s', machine.nr_cpus, machine.nr_cores)

    entry = super(HDTEntry_CPU, cls).create(HDTEntryTypes.CPU)
    entry.nr_cpus = machine.nr_cpus
    entry.nr_cores = machine.nr_cores

    return entry

class HDTEntry_Memory(HDTEntry):
  _pack_ = 0
  _fields_ = [
    ('type',   c_ushort),
    ('length', c_ushort),
    ('size',   c_uint)
  ]

  @classmethod
  def create(cls, machine):
    machine.DEBUG('HDTEntry_Memory.create: size=%s', sizeof_fmt(machine.memory.size))

    entry = super(HDTEntry_Memory, cls).create(HDTEntryTypes.MEMORY)
    entry.size = machine.memory.size

    return entry

class HDT(object):
  klasses = [
    HDTEntry_Memory,
    HDTEntry_CPU,
  ]

  def __init__(self, machine):
    self.machine = machine

    self.header = None
    self.entries = []

  def create(self):
    self.header = HDTHeader.create(self.machine)

    for klass in HDT.klasses:
      self.entries.append(klass.create(self.machine))

    self.header.entries = len(self.entries)

  def size(self):
    return sizeof(HDTHeader) + sum([sizeof(entry) for entry in self.entries])

  def write(self, address):
    address = self.header.write(self.machine, address)

    for entry in self.entries:
      address = entry.write(self.machine, address)

class MachineState(SnapshotNode):
  def __init__(self):
    super(MachineState, self).__init__('nr_cpus', 'nr_cores')

  def get_binary_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('binary_')]

  def get_cpu_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('cpu')]

  def get_cpu_state_by_id(self, cpuid):
    return self.get_children()['cpu{}'.format(cpuid)]

class SymbolCache(LRUCache):
  def __init__(self, machine, size, *args, **kwargs):
    super(SymbolCache, self).__init__(machine.LOGGER, size, *args, **kwargs)

    self.machine = machine

  def get_object(self, address):
    cs = addr_to_segment(address)
    address = address & 0xFFFF

    self.machine.DEBUG('SymbolCache.get_object: cs=%s, address=%s', cs, address)

    for binary in self.machine.binaries:
      if binary.cs != cs:
        continue

      return binary.symbol_table[address]

    return (None, None)

class AddressCache(LRUCache):
  def __init__(self, machine, size, *args, **kwargs):
    super(AddressCache, self).__init__(machine.LOGGER, size, *args, **kwargs)

    self.machine = machine

  def get_object(self, symbol):
    self.machine.DEBUG('AddressCache.get_object: symbol=%s', symbol)

    for csr, dsr, sp, ip, symbols in self.machine.binaries:
      if symbol not in symbols:
        continue

      return (csr, symbols[symbol])

    return None

class BinaryState(SnapshotNode):
  def __init__(self):
    super(BinaryState, self).__init__('path', 'cs', 'ds')

class Binary(ISnapshotable, object):
  binary_id = 0

  def __init__(self, path, run = True, cores = None):
    super(Binary, self).__init__()

    self.id = Binary.binary_id
    Binary.binary_id += 1

    self.run = run

    self.path = path
    self.cs = None
    self.ds = None
    self.ip = None
    self.symbols = None
    self.regions = None
    self.cores = None

    if cores is not None:
      self.cores = []

      for core in cores.split(','):
        cpuid, coreid = core.strip().split(':')
        self.cores.append((int(cpuid), int(coreid)))

    self.raw_binary = None

  def load_symbols(self):
    self.raw_binary.load_symbols()
    self.symbol_table = util.SymbolTable(self.raw_binary)

  def save_state(self, parent):
    state = parent.add_child('binary_{}'.format(self.id), BinaryState())

    state.path = self.path
    state.cs = self.cs
    state.ds = self.ds

    for region in self.regions:
      region.save_state(state)

  def load_state(self, state):
    pass

  def get_init_state(self):
    return [self.cs, self.ds, self.sp, self.ip, False]

class IRQRouterTask(IReactorTask):
  """
  This task is responsible for distributing triggered IRQs between CPU cores.
  When IRQ is triggered, IRQ source (i.e. device that requires attention) is
  appended to this tasks queue (:py:attr:`ducky.machine.IRQRouterTask.qeueu`).
  As long as this queue is not empty, this task pops IRQ sources, selects
  free CPU core, and by calling its :py:meth:`ducky.cpu.CPUCore.irq` method
  core takes reponsibility for executing interrupt routine.

  :param ducky.machine.Machine machine: machine this task belongs to.
  """

  def __init__(self, machine):
    self.machine = machine

    from .devices import IRQList
    self.queue = [False for _ in range(0, IRQList.IRQ_COUNT)]

  def run(self):
    self.machine.DEBUG('irq: router has %i waiting irqs', self.queue.count(True))

    for irq, triggered in enumerate(self.queue):
      if triggered is not True:
        continue

      self.machine.DEBUG('irq: triggered %i', irq)
      for core in self.machine.cores():
        if core.registers.flags.hwint != 1:
          continue

        self.queue[irq] = False
        core.irq(irq)
        break

      else:
        break

    if not any(self.queue):
      self.machine.reactor.task_suspended(self)

class CheckLivingCoresTask(IReactorTask):
  """
  This task checks number of living cores in the VM. If there are no living
  cores, it's safe to halt the VM.

  :param ducky.machine.Machine machine: machine this task belongs to.
  """

  def __init__(self, machine):
    self.machine = machine

  def run(self):
    self.machine.halt()

class Machine(ISnapshotable, IMachineWorker):
  """
  Virtual machine itself.
  """

  def core(self, cid):
    """
    Find CPU core by its string id.

    :param string cid: id of searched CPU core, in the form `#<cpuid>:#<coreid>`.
    :rtype: :py:class:`ducky.cpu.CPUCore`
    :returns: found core
    :raises ducky.errors.InvalidResourceError: when no such core exists.
    """

    for _cpu in self.cpus:
      for _core in _cpu.cores:
        if '#%i:#%i' % (_cpu.id, _core.id) == cid:
          return _core

    raise InvalidResourceError(F('No such CPU core: cid={cid}', cid = cid))

  def __init__(self, logger = None):
    self.reactor = Reactor(self)

    # Setup logging
    self.LOGGER = logger or create_logger()
    self.DEBUG = self.LOGGER.debug
    self.INFO = self.LOGGER.info
    self.WARN = self.LOGGER.warning
    self.ERROR = self.LOGGER.error
    self.EXCEPTION = self.LOGGER.exception

    self.console = ConsoleMaster(self)
    self.console.register_command('halt', cmd_halt)
    self.console.register_command('boot', cmd_boot)
    self.console.register_command('run', cmd_run)
    self.console.register_command('snap', cmd_snapshot)

    self.irq_router_task = IRQRouterTask(self)
    self.reactor.add_task(self.irq_router_task)

    self.cnt_living_cores = 0

    self.check_living_cores_task = CheckLivingCoresTask(self)
    self.reactor.add_task(self.check_living_cores_task)

    self.symbol_cache = SymbolCache(self, 256)
    self.address_cache = AddressCache(self, 256)

    from .cpu import CPUCacheController
    self.cpu_cache_controller = CPUCacheController(self)

    self.binaries = []
    self.init_states = []

    self.cpus = []
    self.memory = None

    self.devices = collections.defaultdict(dict)
    self.ports = {}

    self.hdt = HDT(self)
    self.hdt_address = None

    self.virtual_interrupts = {}

    self.last_state = None

  def cores(self):
    """
    Get list of all cores in the machine.

    :rtype: list
    :returns: `list` of :py:class:`ducky.cpu.CPUCore` instances
    """

    return [c for c in itertools.chain(*[__cpu.cores for __cpu in self.cpus])]

  def core_alive(self):
    """
    Signal machine that one of CPU cores is now alive.
    """

    self.cnt_living_cores += 1

  def core_halted(self):
    """
    Signal machine that one of CPU cores is no longer alive.
    """

    self.cnt_living_cores -= 1

    if self.cnt_living_cores == 0:
      self.reactor.task_runnable(self.check_living_cores_task)

  @property
  def living_cores(self):
    """
    List of all living cores in the machine.

    :rtype: list
    :returns: `list` of :py:class:`ducky.cpu.CPUCore` instances
    """

    return [c for c in itertools.chain(*[__cpu.living_cores for __cpu in self.cpus])]

  def get_device_by_name(self, name, klass = None):
    """
    Get device by its name and class.

    :param string name: name of the device.
    :param string klass: if set, search only devices with this class.
    :rtype: :py:class:`ducky.devices.Device`
    :returns: found device
    :raises ducky.errors.InvalidResourceError: when no such device exists
    """

    self.DEBUG('get_device_by_name: name=%s, klass=%s', name, klass)

    for dev_klass, devs in iteritems(self.devices):
      if klass and dev_klass != klass:
        continue

      for dev_name, dev in iteritems(devs):
        if dev_name != name:
          continue

        return dev

    raise InvalidResourceError(F('No such device: name={name}, klass={klass}', name = name, klass = klass))

  def get_storage_by_id(self, sid):
    """
    Get storage by its id.

    :param int sid: id of storage caller is looking for.
    :rtype: :py:class:`ducky.devices.Device`
    :returns: found device.
    :raises ducky.errors.InvalidResourceError: when no such storage exists.
    """

    self.DEBUG('get_storage_by_id: id=%s', sid)
    self.DEBUG('storages: %s', self.devices['storage'])

    for name, dev in iteritems(self.devices['storage']):
      if dev.sid != sid:
        continue

      return dev

    raise InvalidResourceError(F('No such storage: sid={sid:d}', sid = sid))

  def get_addr_by_symbol(self, symbol):
    return self.address_cache[symbol]

  def get_symbol_by_addr(self, cs, address):
    return self.symbol_cache[segment_addr_to_addr(cs, address)]

  def save_state(self, parent):
    state = parent.add_child('machine', MachineState())

    state.nr_cpus = self.nr_cpus
    state.nr_cores = self.nr_cores

    for binary in self.binaries:
      binary.save_state(state)

    for cpu in self.cpus:
      cpu.save_state(state)

    self.memory.save_state(state)

  def load_state(self, state):
    self.nr_cpus = state.nr_cpus
    self.nr_cores = state.nr_cores

    # ignore binary states

    for __cpu in self.cpus:
      cpu_state = state.get_children().get('cpu{}'.format(__cpu.id))
      if cpu_state is None:
        self.WARN('State of CPU #%i not found!', __cpu.id)
        continue

      __cpu.load_state(cpu_state)

    self.memory.load_state(state.get_children()['memory'])

  def print_regions(self, regions):
    table = [
      ['Section', 'Address', 'Size', 'Flags', 'First page', 'Last page']
    ]

    for r in regions:
      table.append([r.name, ADDR_FMT(r.address), r.size, r.flags, r.pages_start, r.pages_start + r.pages_cnt - 1])

    self.LOGGER.table(table, fn = self.DEBUG)

  def poke(self, address, value, length):
    self.DEBUG('poke: addr=%s, value=%s, length=%s', ADDR_FMT(address), UINT32_FMT(value), length)

    if length == 1:
      self.memory.write_u8(address, UInt8(value).u8, privileged = True)

    elif length == 2:
      self.memory.write_u16(address, UInt16(value).u16, privileged = True)

    else:
      self.memory.write_u32(address, UInt32(value).u32, privileged = True)

  def setup_interrupt_routines(self):
    if not self.config.has_option('machine', 'interrupt-routines'):
      return

    binary = Binary(self.config.get('machine', 'interrupt-routines'), run = False)
    self.binaries.append(binary)

    self.INFO('irq: loading routines from file %s', binary.path)

    binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)
    binary.load_symbols()

    ivt_address = self.config.getint('machine', 'interrupt-table', 0x000000)
    self.DEBUG('IVT: address=%s', ADDR_FMT(ivt_address))

    self.memory.alloc_ivt(ivt_address)

    from .cpu import InterruptVector
    desc = InterruptVector(cs = binary.cs, ds = binary.ds)

    def __save_iv(name, index):
      if name not in binary.symbols:
        self.DEBUG('irq: routine %s not found', name)
        return

      desc.ip = binary.symbols[name].u16
      self.memory.save_interrupt_vector(ivt_address, index, desc)

    from .devices import IRQList
    for i in range(0, IRQList.IRQ_COUNT):
      __save_iv('irq_routine_{}'.format(i), i)

    self.print_regions(binary.regions)

  def setup_binaries(self):
    for binary_section in self.config.iter_binaries():
      binary = Binary(self.config.get(binary_section, 'file'), cores = self.config.get(binary_section, 'cores', None))
      self.binaries.append(binary)

      self.INFO('binary: loading from from file %s', binary.path)

      if binary.cores is None:
        binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)

      else:
        binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path, stack = False)

      binary.load_symbols()

      entry_label = self.config.get(binary_section, 'entry', 'main')
      entry_addr = binary.symbols.get(entry_label)

      if entry_addr is None:
        self.WARN('binary: entry point "%s" not found', entry_label)
        entry_addr = UInt16(0)

      binary.ip = entry_addr.u16

      self.print_regions(binary.regions)

    self.init_states = [[None for _ in range(0, self.nr_cores)] for _ in range(0, self.nr_cpus)]
    self.DEBUG('Machine.setup_binaries: init_states=%s', self.init_states)

    binaries = self.binaries[1:] if self.config.has_option('machine', 'interrupt-routines') else self.binaries

    self.DEBUG('Machine.setup_binaries: solve core affinity')
    for binary in binaries:
      self.DEBUG('  binary #%i', binary.id)

      if binary.cores is None:
        self.DEBUG('    no cores set, skip')
        continue

      for cpuid, coreid in binary.cores:
        if self.init_states[cpuid][coreid] != None:
          raise Exception('Init state #%s:#%s already exists' % (cpuid, coreid))

        self.init_states[cpuid][coreid] = binary.get_init_state()

        sp = self.memory.create_binary_stack(binary.ds, binary.regions)
        self.init_states[cpuid][coreid][2] = sp

    self.DEBUG('Machine.setup_binaries: init_states=%s', self.init_states)

    self.DEBUG('Machine.setup_binaries: fill empty spots')

    for binary in binaries:
      self.DEBUG('  binary #%i', binary.id)

      if binary.cores is not None:
        self.DEBUG('    cores set, skip')
        continue

      for cpuid in range(0, self.nr_cpus):
        for coreid in range(0, self.nr_cores):
          if self.init_states[cpuid][coreid] is not None:
            continue

          self.init_states[cpuid][coreid] = binary.get_init_state()

    self.DEBUG('Machine.setup_binaries: init_states=%s', self.init_states)

  def setup_mmaps(self):
    for section in self.config.iter_mmaps():
      _get, _getbool, _getint = self.config.create_getters(section)

      access = _get('access', 'r')
      flags = SectionFlags(readable = 'r' in access, writable = 'w' in access, executable = 'x' in access)
      self.memory.mmap_area(_get('file'),
                            _getint('address'),
                            _getint('size'),
                            offset = _getint('offset', 0),
                            flags = flags,
                            shared = _getbool('shared', False))

  def setup_devices(self):
    for section in self.config.iter_devices():
      _get, _getbool, _getint = self.config.create_getters(section)

      klass = _get('klass', None)
      driver = _get('driver', None)

      if not klass or not driver:
        self.ERROR('Unknown class or driver of device %s: klass=%s, driver=%s', section, klass, driver)
        continue

      if _getbool('enabled', True) is not True:
        self.DEBUG('Device %s disabled', section)
        continue

      driver = driver.split('.')
      driver_module = importlib.import_module('.'.join(driver[0:-1]))
      driver_class = getattr(driver_module, driver[-1])
      dev = driver_class.create_from_config(self, self.config, section)
      self.devices[klass][section] = dev

      if _get('master', None) is not None:
        dev.master = _get('master')

  def setup_debugging(self):
    for section in self.config.iter_breakpoints():
      _get, _getint, _getbool = self.config.create_getters(section)

      core = self.core(_get('core', '#0:#0'))
      core.init_debug_set()

      klass = _get('klass', 'ducky.debugging.BreakPoint').split('.')
      klass = getattr(importlib.import_module('.'.join(klass[0:-1])), klass[-1])

      p = klass.create_from_config(core.debug, self.config, section)
      core.debug.add_point(p)

  def setup_hdt(self):
    self.DEBUG('Machine.setup_hdt')

    self.hdt.create()

    pages = self.memory.alloc_pages(segment = 0x00, count = align(PAGE_SIZE, self.hdt.size()) // PAGE_SIZE)
    self.memory.update_pages_flags(pages[0].index, len(pages), 'read', True)
    self.hdt_address = pages[0].base_address

    self.DEBUG('Machine.setup_hdt: address=%s, size=%s (%s pages)', ADDR_FMT(self.hdt_address), self.hdt.size(), len(pages))

    self.hdt.write(self.hdt_address)

  def hw_setup(self, machine_config):
    self.config = machine_config

    self.nr_cpus = self.config.getint('machine', 'cpus')
    self.nr_cores = self.config.getint('machine', 'cores')

    self.memory = mm.MemoryController(self, size = machine_config.getint('memory', 'size', 0x1000000))

    self.setup_devices()

    from .cpu import CPU
    for cpuid in range(0, self.nr_cpus):
      self.cpus.append(CPU(self, cpuid, self.memory, self.cpu_cache_controller, cores = self.nr_cores))

    from .devices import VIRTUAL_INTERRUPTS
    for index, cls in iteritems(VIRTUAL_INTERRUPTS):
      self.virtual_interrupts[index] = cls(self)

  @property
  def exit_code(self):
    self.__exit_code = 0

    for __cpu in self.cpus:
      for __core in __cpu.cores:
        if __core.exit_code != 0:
          self.__exit_code = __core.exit_code

    return self.__exit_code

  def register_port(self, port, handler):
    self.DEBUG('Machine.register_port: port=%s, handler=%s', UINT16_FMT(port), handler)

    if port in self.ports:
      raise IndexError('Port already assigned: {}'.format(UINT16_FMT(port)))

    self.ports[port] = handler

  def unregister_port(self, port):
    self.DEBUG('Machine.unregister_port: port=%s', UINT16_FMT(port))

    del self.ports[port]

  def trigger_irq(self, handler):
    self.DEBUG('Machine.trigger_irq: handler=%s', handler)

    self.irq_router_task.queue[handler.irq] = True
    self.reactor.task_runnable(self.irq_router_task)

  def boot(self):
    self.INFO('Ducky VM, version %s', __version__)
    self.INFO('Running on %s', sys.version.replace('\n', ' '))

    self.DEBUG('Machine.boot')

    self.memory.boot()
    self.console.boot()

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.boot()

    self.setup_interrupt_routines()
    self.setup_binaries()
    self.setup_mmaps()
    self.setup_debugging()
    self.setup_hdt()

    for __cpu in self.cpus:
      __cpu.boot()

  def run(self):
    self.DEBUG('Machine.run')

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.run()

    for __cpu in self.cpus:
      __cpu.run()

    self.start_time = time.time()
    self.reactor.run()
    self.end_time = time.time()

  def suspend(self):
    self.DEBUG('Machine.suspend')

    for __cpu in self.cpus:
      __cpu.suspend()

  def wake_up(self):
    self.DEBUG('Machine.wake_up')

    for __cpu in self.cpus:
      __cpu.wake_up()

  def die(self, exc):
    self.DEBUG('Machine.die: exc=%s', exc)

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('Machine.halt')

    self.capture_state()

    for __cpu in self.cpus:
      __cpu.halt()

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.halt()

    self.memory.halt()

    self.console.halt()

    self.reactor.remove_task(self.irq_router_task)
    self.reactor.remove_task(self.check_living_cores_task)

    self.INFO('Halted.')

  def capture_state(self, suspend = False):
    """
    Capture current state of the VM, and store it in it's `last_state` attribute.

    :param bool suspend: if `True`, suspend VM before taking snapshot.
    """

    self.last_state = snapshot.VMState.capture_vm_state(self, suspend = suspend)
    return self.last_state

def cmd_boot(console, cmd):
  """
  Setup HW, load binaries, init everything
  """

  M = console.master.machine

  M.boot()
  M.console.unregister_command('boot')

def cmd_run(console, cmd):
  """
  Start execution of loaded binaries
  """

  M = console.master.machine

  M.run()
  M.console.unregister_command('run')

def cmd_halt(console, cmd):
  """
  Halt execution
  """

  M = console.master.machine

  M.halt()

  M.INFO('VM halted by user')

def cmd_snapshot(console, cmd):
  """
  Create snapshot
  """

  M = console.master.machine

  state = snapshot.VMState.capture_vm_state(M)

  filename = 'ducky-core.{}'.format(os.getpid())
  state.save(filename)

  M.INFO('Snapshot saved as %s', filename)
  console.writeln('Snapshot saved as %s', filename)
