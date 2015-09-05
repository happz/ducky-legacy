"""
:py:class:`ducky.machine.Machine` is *the* virtual machine. Each instance
represents self-contained virtual machine, with all its devices, memory, CPUs
and other necessary properties.
"""

import functools
import itertools
import collections
import importlib
import os

from . import mm
from . import snapshot
from . import util

from . import __version__

from .interfaces import IMachineWorker, ISnapshotable, IReactorTask

from .console import ConsoleMaster
from .errors import InvalidResourceError
from .log import create_logger
from .util import str2int, LRUCache, F
from .mm import addr_to_segment, ADDR_FMT, segment_addr_to_addr, UInt16, UINT16_FMT
from .reactor import Reactor
from .snapshot import SnapshotNode

class MachineState(SnapshotNode):
  def __init__(self):
    super(MachineState, self).__init__('nr_cpus', 'nr_cores')

  def get_binary_states(self):
    return [__state for __name, __state in self.get_children().iteritems() if __name.startswith('binary_')]

  def get_core_states(self):
    return [__state for __name, __state in self.get_children().iteritems() if __name.startswith('core')]

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

    else:
      return None

class BinaryState(SnapshotNode):
  def __init__(self):
    super(BinaryState, self).__init__('path', 'cs', 'ds')

class Binary(ISnapshotable, object):
  binary_id = 0

  def __init__(self, path, run = True):
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

    self.raw_binary = None

  def load_symbols(self):
    self.raw_binary.load_symbols()
    self.symbol_table = util.SymbolTable(self.raw_binary)

  def save_state(self, parent):
    state = parent.add_child('binary_{}'.format(self.id), BinaryState())

    state.path = self.path
    state.cs = self.cs
    state.ds = self.ds

    map(lambda region: region.save_state(state), self.regions)

  def load_state(self, state):
    pass

  def get_init_state(self):
    return (self.cs, self.ds, self.sp, self.ip, False)

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

    self.queue = []

  def runnable(self):
    return self.queue

  def run(self):
    while self.queue:
      self.machine.cpus[0].cores[0].irq(self.queue.pop(0).irq)

class CheckLivingCoresTask(IReactorTask):
  """
  This task checks number of living cores in the VM. If there are no living
  cores, it's safe to halt the VM.

  :param ducky.machine.Machine machine: machine this task belongs to.
  """

  def __init__(self, machine):
    self.machine = machine

  def runnable(self):
    return len(self.machine.living_cores()) == 0

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

  def __init__(self):
    self.reactor = Reactor(self)

    # Setup logging
    self.LOGGER = create_logger()
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

    self.check_living_cores_task = CheckLivingCoresTask(self)
    self.reactor.add_task(self.check_living_cores_task)

    self.symbol_cache = SymbolCache(self, 256)
    self.address_cache = AddressCache(self, 256)

    self.binaries = []

    self.cpus = []
    self.memory = None

    self.devices = collections.defaultdict(dict)
    self.ports = {}

    self.virtual_interrupts = {}

    self.last_state = None

  def cores(self):
    """
    Get list of all cores in the machine.

    :rtype: list
    :returns: `list` of :py:class:`ducky.cpu.CPUCore` instances
    """

    return itertools.chain(*[__cpu.cores for __cpu in self.cpus])

  def living_cores(self):
    """
    Get list of all living cores in the machine.

    :rtype: list
    :returns: `list` of :py:class:`ducky.cpu.CPUCore` instances
    """

    return itertools.chain(*[__cpu.living_cores() for __cpu in self.cpus])

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

    for dev_klass, devs in self.devices.iteritems():
      if klass and dev_klass != klass:
        continue

      for dev_name, dev in devs.iteritems():
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

    for name, dev in self.devices['storage'].iteritems():
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

    map(lambda binary: binary.save_state(state), self.binaries)
    map(lambda __core: __core.save_state(state), self.cores())
    self.memory.save_state(state)

  def load_state(self, state):
    self.nr_cpus = state.nr_cpus
    self.nr_cores = state.nr_cores

    # ignore binary states

    for __cpu in self.cpus:
      cpu_state = state.get_children().get('cpu{}'.format(__cpu.id), None)
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

  def load_interrupt_routines(self):
    binary = Binary(self.config.get('machine', 'interrupt-routines'), run = False)
    self.binaries.append(binary)

    self.INFO('irq: loading routines from file %s', binary.path)

    binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)
    binary.load_symbols()

    from .cpu import InterruptVector
    desc = InterruptVector()
    desc.cs = binary.cs
    desc.ds = binary.ds

    def __save_iv(name, table, index):
      if name not in binary.symbols:
        self.DEBUG('irq: routine %s not found', name)
        return

      desc.ip = binary.symbols[name].u16
      self.memory.save_interrupt_vector(table, index, desc)

    from .devices import IRQList
    for i in range(0, IRQList.IRQ_COUNT):
      __save_iv('irq_routine_{}'.format(i), self.memory.irq_table_address, i)

    from .devices import InterruptList
    for i in range(0, InterruptList.INT_COUNT):
      __save_iv('int_routine_{}'.format(i), self.memory.int_table_address, i)

    self.print_regions(binary.regions)

  def load_binaries(self):
    for binary_section in self.config.iter_binaries():
      binary = Binary(self.config.get(binary_section, 'file'))
      self.binaries.append(binary)

      self.INFO('binary: loading from from file %s', binary.path)

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)
      binary.load_symbols()

      entry_label = self.config.get(binary_section, 'entry', 'main')
      entry_addr = binary.symbols.get(entry_label, None)

      if entry_addr is None:
        self.WARN('binary: entry point "%s" not found', entry_label)
        entry_addr = UInt16(0)

      binary.ip = entry_addr.u16

      self.print_regions(binary.regions)

  def hw_setup(self, machine_config):
    self.config = machine_config

    self.nr_cpus = self.config.getint('machine', 'cpus')
    self.nr_cores = self.config.getint('machine', 'cores')

    self.memory = mm.MemoryController(self)

    from .cpu import CPUCacheController
    self.cpu_cache_controller = CPUCacheController(self)

    from .cpu import CPU
    for cpuid in range(0, self.nr_cpus):
      self.cpus.append(CPU(self, cpuid, self.memory, self.cpu_cache_controller, cores = self.nr_cores))

    self.memory.boot()

    # Devices
    for st_section in self.config.iter_devices():
      _get     = functools.partial(self.config.get, st_section)
      _getbool = functools.partial(self.config.getbool, st_section)
      _getint  = functools.partial(self.config.getint, st_section)

      klass = _get('klass', None)
      driver = _get('driver', None)

      if not klass or not driver:
        self.ERROR('Unknown class or driver of device %s: klass=%s, driver=%s', st_section, klass, driver)
        continue

      if _getbool('enabled', True) is not True:
        self.DEBUG('Device %s disabled', st_section)
        continue

      driver = driver.split('.')
      driver_module = importlib.import_module('.'.join(driver[0:-1]))
      driver_class = getattr(driver_module, driver[-1])
      dev = driver_class.create_from_config(self, self.config, st_section)
      self.devices[klass][st_section] = dev

      if _get('master', None) is not None:
        dev.master = _get('master')

    from .devices import VIRTUAL_INTERRUPTS
    for index, cls in VIRTUAL_INTERRUPTS.iteritems():
      self.virtual_interrupts[index] = cls(self)

    for mmap_section in self.config.iter_mmaps():
      _get     = functools.partial(self.config.get, mmap_section)
      _getbool  = functools.partial(self.config.getbool, mmap_section)
      _getint  = functools.partial(self.config.getint, mmap_section)

      self.memory.mmap_area(_get('file'),
                            _getint('address'),
                            _getint('size'),
                            offset = _getint('offset', 0),
                            access = _get('access', 'r'),
                            shared = _getbool('shared', False))

    # Breakpoints
    from .debugging import add_breakpoint

    for bp_section in self.config.iter_breakpoints():
      _get     = functools.partial(self.config.get, bp_section)
      _getbool = functools.partial(self.config.getbool, bp_section)
      _getint  = functools.partial(self.config.getint, bp_section)

      core = self.core(_get('core', '#0:#0'))

      address = _get('address', '0x000000')
      if address[0].isdigit():
        address = UInt16(str2int(address))

      else:
        for binary in self.binaries:
          symbol_address = binary.symbols.get(address, None)
          if symbol_address is not None:
            address = symbol_address
            break

      if address is None:
        self.ERROR('Unknown breakpoint address: %s on %s', _get('address', '0x000000'), _get('core', '#0:#0'))
        continue

      add_breakpoint(core, address.u16, ephemeral = _getbool('ephemeral', False), countdown = _getint('countdown', 0))

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
    self.irq_router_task.queue.append(handler)

  def boot(self):
    self.INFO('Ducky VM, version %s', __version__)

    self.DEBUG('Machine.boot')

    self.console.boot()

    for devs in self.devices.itervalues():
      map(lambda dev: dev.boot(), [dev for dev in devs.itervalues() if not dev.is_slave()])

    if self.config.has_option('machine', 'interrupt-routines'):
      self.load_interrupt_routines()

    self.load_binaries()

    init_states = [binary.get_init_state() for binary in self.binaries if binary.run]
    map(lambda __cpu: __cpu.boot(init_states), self.cpus)

  def run(self):
    self.DEBUG('Machine.run')

    for devs in self.devices.itervalues():
      map(lambda dev: dev.run(), [dev for dev in devs.itervalues() if not dev.is_slave()])

    map(lambda __cpu: __cpu.run(), self.cpus)

    self.reactor.run()

  def suspend(self):
    self.DEBUG('Machine.suspend')

    map(lambda __cpu: __cpu.suspend(), self.cpus)

  def wake_up(self):
    self.DEBUG('Machine.wake_up')

    map(lambda __cpu: __cpu.wake_up(), self.cpus)

  def die(self, exc):
    self.DEBUG('Machine.die: exc=%s', exc)

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('Machine.halt')

    self.capture_state()

    map(lambda __cpu: __cpu.halt(), self.cpus)

    for devs in self.devices.itervalues():
      map(lambda dev: dev.halt(), [dev for dev in devs.itervalues() if not dev.is_slave()])

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
