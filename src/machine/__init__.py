import functools
import os
import Queue
import sys
import tabulate
import time
import types

import core
import cpu
import mm
import machine.bus
import profiler

from cpu.errors import InvalidResourceError
from util import debug, info, error, str2int, LRUCache, warn, print_table
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT, segment_base_addr, UInt16, addr_to_segment, segment_addr_to_addr, UInt8

import irq
import irq.conio
import irq.virtual

import io_handlers
import io_handlers.conio

from threading2 import Thread

class SymbolCache(LRUCache):
  def __init__(self, machine, size, *args, **kwargs):
    super(SymbolCache, self).__init__(size, *args, **kwargs)

    self.machine = machine

  def get_object(self, address):
    cs = UInt8(addr_to_segment(address))
    address = UInt16(address & 0xFFFF)

    debug('SymbolCache.get_object: cs=%s, address=%s', cs, address)

    for binary in self.machine.binaries:
      if binary.cs.u8 != cs.u8:
        continue

      last_symbol = None
      last_symbol_offset = UInt16(0xFFFE)

      for symbol_name, symbol_address in binary.symbols.items():
        if symbol_address.u16 > address.u16:
          continue

        if symbol_address.u16 == address.u16:
          return (symbol_name, UInt16(0))

        offset = abs(address.u16 - symbol_address.u16)
        if offset < last_symbol_offset.u16:
          last_symbol = symbol_name
          last_symbol_offset = UInt16(offset)

      return (last_symbol, last_symbol_offset)

    return (None, None)

class AddressCache(LRUCache):
  def __init__(self, machine, size, *args, **kwargs):
    super(AddressCache, self).__init__(size, *args, **kwargs)

    self.machine = machine

  def get_object(self, symbol):
    from cpu.assemble import Label

    debug('AddressCache.get_object: symbol=%s', symbol)

    for csr, dsr, sp, ip, symbols in self.machine.binaries:
      if symbol not in symbols:
        continue

      return (UInt8(csr.u8), symbols[symbol])

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

  def get_init_state(self):
    return (self.cs, self.ds, self.sp, self.ip, False)

class Machine(object):
  def core(self, core_address):
    if type(core_address) == types.TupleType:
      cpuid, coreid = core_address

    else:
      core_address = core_address.split(':')
      cpuid, coreid = (int(core_address[0][1:]), int(core_address[1][1:]))

    return self.cpus[cpuid].cores[coreid]

  def for_each_cpu(self, callback, *args, **kwargs):
    for __cpu in self.cpus:
      callback(__cpu, *args, **kwargs)

  def for_each_core(self, callback, *args, **kwargs):
    for __cpu in self.cpus:
      for __core in __cpu.cores:
        callback(__core, *args, **kwargs)

  def for_core(self, core_address, callback, *args, **kwargs):
    callback(self.core(core_address), *args, **kwargs)

  def for_each_irq(self, callback, *args, **kwargs):
    for src in self.irq_sources:
      if not src:
        continue

      callback(src, *args, **kwargs)

  def cores(self):
    l = []

    self.for_each_core(lambda __core, __cores: __cores.append(__core), l)

    return l

  def living_cores(self):
    return [c for c in self.cores() if c.is_alive()]

  def running_cores(self):
    return [c for c in self.cores() if not c.is_suspended()]

  def get_storage_by_id(self, id):
    debug('get_storage_by_id: id=%s', id)
    debug('storages: %s', str(self.storages))

    return self.storages.get(id, None)

  def get_addr_by_symbol(self, symbol):
    return self.address_cache[symbol]

  def get_symbol_by_addr(self, cs, address):
    return self.symbol_cache[segment_addr_to_addr(cs.u8, address)]

  def hw_setup(self, machine_config, machine_in = None, machine_out = None):
    def __print_regions(regions):
      table = [
        ['Section', 'Address', 'Size', 'Flags', 'First page', 'Last page']
      ]

      for r in regions:
        table.append([r.name, ADDR_FMT(r.address), r.size, r.flags, r.pages_start, r.pages_start + r.pages_cnt - 1])

      print_table(table)

    self.config = machine_config

    self.profiler = profiler.STORE.get_profiler()

    self.nr_cpus = self.config.getint('machine', 'cpus')
    self.nr_cores = self.config.getint('machine', 'cores')

    self.symbol_cache = SymbolCache(self, 256)
    self.address_cache = AddressCache(self, 256)

    self.binaries = []

    self.cpus = []
    self.memory = mm.MemoryController()
    self.ports = io_handlers.IOPortSet()
    self.irq_sources = irq.IRQSourceSet()

    self.wake_up_all_event = None

    self.keep_running = True
    self.thread = None

    self.memory = mm.MemoryController()

    self.message_bus = bus.MessageBus()

    for cpuid in range(0, self.nr_cpus):
      self.cpus.append(cpu.CPU(self, cpuid, cores = self.nr_cores, memory_controller = self.memory))

    self.conio = io_handlers.conio.ConsoleIOHandler(machine_in, machine_out)
    self.conio.echo = True

    self.register_port(0x100, self.conio)
    self.register_port(0x101, self.conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console(self, self.conio))
    #self.register_irq_source(irq.IRQList.TIMER, irq.timer.Timer(10))

    self.memory.boot()

    self.virtual_interrupts = {}
    for index, cls in irq.virtual.VIRTUAL_INTERRUPTS.iteritems():
      self.virtual_interrupts[index] = cls(self)

    if self.config.has_option('machine', 'interrupt-routines'):
      binary = Binary(self.config.get('machine', 'interrupt-routines'), run = False)
      self.binaries.append(binary)

      info('Loading IRQ routines from file %s', binary.path)

      from mm import UInt8, UInt16, UInt24

      binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions = self.memory.load_file(binary.path)

      desc = cpu.InterruptVector()
      desc.cs = binary.cs.u8
      desc.ds = binary.ds.u8

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
      binary.ip = binary.symbols.get(entry_label)

      if not binary.ip:
        warn('Entry point "%s" not found', entry_label)
        binary.ip = mm.UInt16(0)

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
          address = address[1].u16

      if not address:
        error('Unknown breakpoint address: %s on %s', _get('address', '0x000000'), _get('core', '#0:#0'))
        continue

      p = add_breakpoint(core, address, ephemeral = _getbool('ephemeral', False), countdown = _getint('countdown', 0))

    # Storage
    from storage import STORAGES, StorageIOHandler

    self.storageio = StorageIOHandler(self)

    self.storages = {}

    for st_section in self.config.iter_storages():
      _get     = functools.partial(self.config.get, st_section)
      _getbool = functools.partial(self.config.getbool, st_section)
      _getint  = functools.partial(self.config.getint, st_section)

      s_type, s_id, s_data = storage_desc.split(',')

      self.storages[_getint('id')] = STORAGES[_get('type')](self, _getint('id'), _get('file'))

    self.register_port(0x200, self.storageio)
    self.register_port(0x202, self.storageio)

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

  def loop(self):
    self.profiler.enable()

    while self.keep_running:
      time.sleep(10 * cpu.CPU_SLEEP_QUANTUM)

      if len([_cpu for _cpu in self.cpus if _cpu.thread.is_alive()]) == 0:
        info('Machine halted')
        break

    self.profiler.disable()

  def boot(self):
    for handler in self.ports:
      handler.boot()

    self.for_each_irq(lambda src: src.boot())

    for storage in self.storages.values():
      storage.boot()

    init_states = [binary.get_init_state() for binary in self.binaries if binary.run]
    self.for_each_cpu(lambda __cpu, machine: __cpu.boot(init_states), self)

    info('Guest terminal available at %s', self.conio.get_terminal_dev())

  def run(self):
    for handler in self.ports:
      handler.run()

    self.for_each_cpu(lambda __cpu: __cpu.run())

    self.thread = Thread(target = self.loop, name = 'Machine', priority = 0.0)
    self.thread.start()

  def suspend(self):
    suspend_msg = bus.SuspendCore(bus.ADDRESS_LIST, audience = self.running_cores())

    self.message_bus.publish(suspend_msg)
    suspend_msg.wait()
    self.wake_up_all_event = suspend_msg.wake_up

  def wake_up(self):
    if not self.wake_up_all_event:
      return

    self.wake_up_all_event.set()
    self.wake_up_all_event = None

  def halt(self):
    halt_msg = bus.HaltCore(bus.ADDRESS_ALL, audience = self.living_cores())

    self.message_bus.publish(halt_msg)

    self.for_each_core(lambda __core: __core.wake_up())

    halt_msg.wait()

    self.for_each_irq(lambda src: src.halt())

    for handler in self.ports:
      handler.halt()

    for storage in self.storages.values():
      storage.halt()

    if not self.thread:
      self.thread = Thread(target = self.loop, name = 'Machine', priority = 0.0)

  def wait(self):
    while not self.thread or self.thread.is_alive():
      time.sleep(cpu.CPU_SLEEP_QUANTUM * 10)

import console

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

  state = core.VMState.capture_vm_state(console.machine)

  filename = 'ducky-core.%s' % os.getpid()
  state.save(filename)

  console.info('Snapshot saved as %s', filename)

console.Console.register_command('halt', cmd_halt)
console.Console.register_command('boot', cmd_boot)
console.Console.register_command('run', cmd_run)
console.Console.register_command('snap', cmd_snapshot)
