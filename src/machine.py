import functools
import os

import mm
import reactor
import util

from console import Console
from errors import InvalidResourceError
from util import debug, info, error, str2int, LRUCache, warn, print_table, exception
from mm import addr_to_segment, ADDR_FMT, segment_addr_to_addr

class MachineWorker(object):
  def run(self):
    pass

  def suspend(self):
    pass

  def wake_up(self):
    pass

  def die(self, exc):
    pass

  def halt(self):
    pass

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

class Binary(object):
  def __init__(self, path, run = True):
    super(Binary, self).__init__()

    self.run = run

    self.path = path
    self.cs = None
    self.ds = None
    self.ip = None
    self.symbols = None
    self.regions = None

    self.symbol_table = util.SymbolTable(self)

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

class Machine(MachineWorker):
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

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console(self, self.conio))

    self.memory.boot()

    for index, cls in irq.virtual.VIRTUAL_INTERRUPTS.iteritems():
      self.virtual_interrupts[index] = cls(self)

    if self.config.has_option('machine', 'interrupt-routines'):
      binary = Binary(self.config.get('machine', 'interrupt-routines'), run = False)
      self.binaries.append(binary)

      info('Loading IRQ routines from file %s', binary.path)

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions = self.memory.load_file(binary.path)

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

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions = self.memory.load_file(binary.path)

      entry_label = self.config.get(binary_section, 'entry', 'main')
      binary.ip = binary.symbols.get(entry_label).u16

      if not binary.ip:
        warn('Entry point "%s" not found', entry_label)
        binary.ip = 0

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

  import core

  state = core.VMState.capture_vm_state(console.machine)

  filename = 'ducky-core.%s' % os.getpid()
  state.save(filename)

  console.info('Snapshot saved as %s', filename)

Console.register_command('halt', cmd_halt)
Console.register_command('boot', cmd_boot)
Console.register_command('run', cmd_run)
Console.register_command('snap', cmd_snapshot)
