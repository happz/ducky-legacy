import functools
import os

from . import mm
from . import reactor
from . import snapshot
from . import util

from .console import Console
from .errors import InvalidResourceError
from .util import debug, info, error, str2int, LRUCache, warn, print_table, exception
from .mm import addr_to_segment, ADDR_FMT, segment_addr_to_addr, UInt16
from .snapshot import ISnapshotable, SnapshotNode

class MachineWorker(object):
  """
  Base class for objects that provide pluggable service to others.
  """

  def boot(self, *args):
    """
    Prepare for providing the service. After this call, it may be requested
    by others.
    """

    pass

  def run(self):
    """
    Called by reactor's loop when this object is enqueued as a reactor task.
    """

    pass

  def suspend(self):
    """
    Suspend service. Object should somehow conserve its internal state, its
    service will not be used until the next call of ``wake_up`` method.
    """

    pass

  def wake_up(self):
    """
    Wake up service. In this method, object should restore its internal state,
    and after this call its service can be requested by others again.
    """

    pass

  def die(self, exc):
    """
    Exceptional state requires immediate termination of service. Probably no
    object will ever have need to call others' ``die`` method, it's intended
    for internal use only.
    """

    pass

  def halt(self):
    """
    Terminate service. It will never be requested again, object can destroy
    its internal state, and free allocated resources.
    """

    pass

class MachineState(SnapshotNode):
  def __init__(self):
    super(MachineState, self).__init__('nr_cpus', 'nr_cores')

  def get_binary_states(self):
    return [__state for __name, __state in self.get_children().iteritems() if __name.startswith('binary_')]

  def get_core_states(self):
    return [__state for __name, __state in self.get_children().iteritems() if __name.startswith('core')]

class SymbolCache(LRUCache):
  def __init__(self, _machine, size, *args, **kwargs):
    super(SymbolCache, self).__init__(size, *args, **kwargs)

    self.machine = _machine

  def get_object(self, address):
    cs = addr_to_segment(address)
    address = address & 0xFFFF

    debug('SymbolCache.get_object: cs=%s, address=%s', cs, address)

    for binary in self.machine.binaries:
      if binary.cs != cs:
        continue

      return binary.symbol_table[address]

    return (None, None)

class AddressCache(LRUCache):
  def __init__(self, machine, size, *args, **kwargs):
    super(AddressCache, self).__init__(size, *args, **kwargs)

    self.machine = machine

  def get_object(self, symbol):
    debug('AddressCache.get_object: symbol=%s', symbol)

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
    state = parent.add_child('binary_%i' % self.id, BinaryState())

    state.path = self.path
    state.cs = self.cs
    state.ds = self.ds

    map(lambda region: region.save_state(state), self.regions)

  def load_state(self, state):
    pass

  def get_init_state(self):
    return (self.cs, self.ds, self.sp, self.ip, False)

class IRQRouterTask(reactor.ReactorTask):
  def __init__(self, machine):
    self.machine = machine

    self.queue = []

  def runnable(self):
    return True

  def run(self):
    while self.queue:
      self.machine.cpus[0].cores[0].irq(self.queue.pop(0).irq)

class CheckLivingCoresTask(reactor.ReactorTask):
  def __init__(self, machine):
    self.machine = machine

  def runnable(self):
    return len(self.machine.living_cores()) == 0

  def run(self):
    self.machine.halt()

class Machine(ISnapshotable, MachineWorker):
  def __init__(self):
    self.reactor = reactor.reactor

    self.irq_router_task = IRQRouterTask(self)
    self.reactor.add_task(self.irq_router_task)

    self.check_living_cores_task = CheckLivingCoresTask(self)
    self.reactor.add_task(self.check_living_cores_task)

    self.symbol_cache = SymbolCache(self, 256)
    self.address_cache = AddressCache(self, 256)

    self.binaries = []

    self.cpus = []
    self.memory = None

    import io_handlers
    self.ports = io_handlers.IOPortSet()

    import irq
    self.irq_sources = irq.IRQSourceSet()

    self.virtual_interrupts = {}
    self.storages = {}

  def cores(self):
    __cores = []
    map(lambda __cpu: __cores.extend(__cpu.cores), self.cpus)
    return __cores

  def living_cores(self):
    __cores = []
    map(lambda __cpu: __cores.extend(__cpu.living_cores()), self.cpus)
    return __cores

  def get_storage_by_id(self, id):
    debug('get_storage_by_id: id=%s', id)
    debug('storages: %s', str(self.storages))

    return self.storages.get(id, None)

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
      cpu_state = state.get_children().get('cpu%i' % __cpu.id, None)
      if cpu_state is None:
        warn('State of CPU #%i not found!', __cpu.id)
        continue

      __cpu.load_state(cpu_state)

    self.memory.load_state(state.get_children()['memory'])

  def hw_setup(self, machine_config, machine_in = None, machine_out = None):
    import irq
    import irq.conio
    import irq.virtual

    import io_handlers
    import io_handlers.conio

    def __print_regions(regions):
      table = [
        ['Section', 'Address', 'Size', 'Flags', 'First page', 'Last page']
      ]

      for r in regions:
        table.append([r.name, ADDR_FMT(r.address), r.size, r.flags, r.pages_start, r.pages_start + r.pages_cnt - 1])

      print_table(table)

    self.config = machine_config

    self.nr_cpus = self.config.getint('machine', 'cpus')
    self.nr_cores = self.config.getint('machine', 'cores')

    self.memory = mm.MemoryController(self)

    import cpu

    for cpuid in range(0, self.nr_cpus):
      self.cpus.append(cpu.CPU(self, cpuid, cores = self.nr_cores, memory_controller = self.memory))

    self.conio = io_handlers.conio.ConsoleIOHandler(machine_in, machine_out, self)
    self.conio.echo = True

    self.register_port(0x100, self.conio)
    self.register_port(0x101, self.conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.ConsoleIRQ(self, self.conio))

    self.memory.boot()

    for index, cls in irq.virtual.VIRTUAL_INTERRUPTS.iteritems():
      self.virtual_interrupts[index] = cls(self)

    if self.config.has_option('machine', 'interrupt-routines'):
      binary = Binary(self.config.get('machine', 'interrupt-routines'), run = False)
      self.binaries.append(binary)

      info('Loading IRQ routines from file %s', binary.path)

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)
      binary.load_symbols()

      desc = cpu.InterruptVector()
      desc.cs = binary.cs
      desc.ds = binary.ds

      def __save_iv(name, table, index):
        if name not in binary.symbols:
          debug('Interrupt routine %s not found', name)
          return

        desc.ip = binary.symbols[name].u16
        self.memory.save_interrupt_vector(table, index, desc)

      for i in range(0, irq.IRQList.IRQ_COUNT):
        __save_iv('irq_routine_%i' % i, self.memory.irq_table_address, i)

      for i in range(0, irq.InterruptList.INT_COUNT):
        __save_iv('int_routine_%i' % i, self.memory.int_table_address, i)

      __print_regions(binary.regions)

      info('')

    for binary_section in self.config.iter_binaries():
      binary = Binary(self.config.get(binary_section, 'file'))
      self.binaries.append(binary)

      info('Loading binary from file %s', binary.path)

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions, binary.raw_binary = self.memory.load_file(binary.path)
      binary.load_symbols()

      entry_label = self.config.get(binary_section, 'entry', 'main')
      entry_addr = binary.symbols.get(entry_label, None)

      if entry_addr is None:
        warn('Entry point "%s" of binary %s not found', entry_label, binary.path)
        entry_addr = UInt16(0)

      binary.ip = entry_addr.u16

      __print_regions(binary.regions)

      info('')

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
    from debugging import add_breakpoint

    for bp_section in self.config.iter_breakpoints():
      _get     = functools.partial(self.config.get, bp_section)
      _getbool = functools.partial(self.config.getbool, bp_section)
      _getint  = functools.partial(self.config.getint, bp_section)

      core = self.core(_get('core', '#0:#0'))

      address = _get('address', '0x000000')
      if address[0].isdigit():
        address = str2int(address)

      else:
        address = self.get_addr_by_symbol(address)
        if address:
          address = address[1]

      if not address:
        error('Unknown breakpoint address: %s on %s', _get('address', '0x000000'), _get('core', '#0:#0'))
        continue

      add_breakpoint(core, address, ephemeral = _getbool('ephemeral', False), countdown = _getint('countdown', 0))

    # Storage
    from blockio import STORAGES

    for st_section in self.config.iter_storages():
      _get     = functools.partial(self.config.get, st_section)
      _getbool = functools.partial(self.config.getbool, st_section)
      _getint  = functools.partial(self.config.getint, st_section)

      self.storages[_getint('id')] = STORAGES[_get('driver')](self, _getint('id'), _get('file'))

  @property
  def exit_code(self):
    self.__exit_code = 0

    for __cpu in self.cpus:
      for __core in __cpu.cores:
        if __core.exit_code != 0:
          self.__exit_code = __core.exit_code

    return self.__exit_code

  def register_irq_source(self, index, src, reassign = False):
    if self.irq_sources[index]:
      if not reassign:
        raise InvalidResourceError('IRQ already assigned: %i' % index)

      for i in range(0, len(self.irq_sources)):
        if not self.irq_sources[i]:
          index = i
          break
      else:
        raise InvalidResourceError('IRQ already assigned, no available free IRQ: %i' % index)

    self.irq_sources[index] = src
    src.irq = index
    return index

  def unregister_irq_source(self, index):
    self.irq_sources[index] = None

  def register_port(self, port, handler):
    if port in self.ports:
      raise IndexError('Port already assigned: %i' % port)

    self.ports[port] = handler

  def unregister_port(self, port):
    del self.ports[port]

  def trigger_irq(self, handler):
    self.irq_router_task.queue.append(handler)

  def boot(self):
    debug('Machine.boot')

    map(lambda __port: __port.boot(), self.ports)
    map(lambda __irq: __irq.boot(), [irq_source for irq_source in self.irq_sources if irq_source is not None])
    map(lambda __storage: __storage.boot(), self.storages.itervalues())

    init_states = [binary.get_init_state() for binary in self.binaries if binary.run]
    map(lambda __cpu: __cpu.boot(init_states), self.cpus)

    info('Guest terminal available at %s', self.conio.get_terminal_dev())

  def run(self):
    debug('Machine.run')

    map(lambda __port: __port.run(), self.ports)
    map(lambda __irq: __irq.run(), [irq_source for irq_source in self.irq_sources if irq_source is not None])
    map(lambda __storage: __storage.run(), self.storages.itervalues())

    map(lambda __cpu: __cpu.run(), self.cpus)

    self.reactor.run()

  def suspend(self):
    debug('Machine.suspend')

    map(lambda __cpu: __cpu.suspend(), self.cpus)

  def wake_up(self):
    debug('Machine.wake_up')

    map(lambda __cpu: __cpu.wake_up(), self.cpus)

  def die(self, exc):
    debug('Machine.die: exc=%s', exc)

    exception(exc)

    self.halt()

  def halt(self):
    debug('Machine.halt')

    map(lambda __irq: __irq.halt(),         [irq_source for irq_source in self.irq_sources if irq_source is not None])
    map(lambda __port: __port.halt(),       self.ports)
    map(lambda __storage: __storage.halt(), self.storages.itervalues())
    map(lambda __cpu: __cpu.halt(),         self.cpus)

    self.reactor.remove_task(self.irq_router_task)
    self.reactor.remove_task(self.check_living_cores_task)

  def snapshot(self, path):
    state = snapshot.VMState.capture_vm_state(self, suspend = False)
    state.save(path)
    info('VM snapshot save in %s', path)

def cmd_boot(console, cmd):
  """
  Setup HW, load binaries, init everything
  """

  console.machine.boot()
  console.Console.unregister_command('boot')

def cmd_run(console, cmd):
  """
  Start execution of loaded binaries
  """

  console.machine.run()
  console.Console.unregister_command('run')

def cmd_halt(console, cmd):
  """
  Halt execution
  """

  console.info('VM halted by user')

  console.machine.halt()
  console.halt()

def cmd_snapshot(console, cmd):
  """
  Create snapshot
  """

  state = snapshot.VMState.capture_vm_state(console.machine)

  filename = 'ducky-core.%s' % os.getpid()
  state.save(filename)

  console.info('Snapshot saved as %s', filename)

Console.register_command('halt', cmd_halt)
Console.register_command('boot', cmd_boot)
Console.register_command('run', cmd_run)
Console.register_command('snap', cmd_snapshot)
