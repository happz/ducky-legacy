import Queue
import sys
import time
import threading
import types

import cpu
import mm
import machine.bus

from cpu.errors import InvalidResourceError
from util import debug, info, warn
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT, segment_base_addr, UInt16

import irq
import io_handlers

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

  def get_storage_by_id(self, id):
    debug('get_storage_by_id: id=%s' % id)
    debug('storages: %s' % str(self.storages))

    return self.storages.get(id, None)

  def get_symbol_by_addr(self, cs, address):
    for csr, dsr, sp, ip, symbols in self.binaries:
      if csr.u8 != cs.u8:
        continue

      last_symbol = None
      last_symbol_offset = UInt16(0xFFFE)

      for symbol_name, symbol_address in symbols.items():
        if symbol_address.u16 > address:
          continue

        if symbol_address.u16 == address:
          return (symbol_name, UInt16(0))

        offset = abs(address - symbol_address.u16)
        if offset < last_symbol_offset.u16:
          last_symbol = symbol_name
          last_symbol_offset = UInt16(offset)

      return (last_symbol, last_symbol_offset)

    return (None, None)

  def hw_setup(self, cpus = 1, cores = 1, memory_size = None, binaries = None, breakpoints = None, irq_routines = None, storages = None):
    self.nr_cpus = cpus
    self.nr_cores = cores

    binaries = binaries or []
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

    for cpuid in range(0, cpus):
      self.cpus.append(cpu.CPU(self, cpuid, cores = cores, memory_controller = self.memory))

    self.conio = io_handlers.conio.ConsoleIOHandler()
    self.conio.echo = True
    self.conio.crlf = True

    self.register_port(0x100, self.conio)
    self.register_port(0x101, self.conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console(self.conio))
    #self.register_irq_source(irq.IRQList.TIMER, irq.timer.Timer(10))

    self.memory.boot()

    if irq_routines:
      info('Loading IRQ routines from file %s' % irq_routines)

      from mm import UInt8, UInt16, UInt24

      csr, dsr, sp, ip, symbols = self.memory.load_file(irq_routines)
      self.binaries.append((csr, dsr, sp, ip, symbols))

      desc = cpu.InterruptVector()
      desc.cs = csr.u8
      desc.ds = dsr.u8

      def __save_iv(name, table, index):
        if name not in symbols:
          warn('Interrupt routine %s not found' % name)
          return

        desc.ip = symbols[name].u16
        self.memory.save_interrupt_vector(table, index, desc)

      __save_iv('irq_timer', self.memory.irq_table_address, irq.IRQList.TIMER)
      __save_iv('irq_conio', self.memory.irq_table_address, irq.IRQList.CONIO)

      __save_iv('int_halt', self.memory.int_table_address, 0)
      __save_iv('int_read_blocks', self.memory.int_table_address, 1)
      __save_iv('int_write_blocks', self.memory.int_table_address, 2)

    self.init_states = []

    for bc_file in binaries:
      csr, dsr, sp, ip, symbols = self.memory.load_file(bc_file)

      debug('init state: csr=%s, dsr=%s, sp=%s, ip=%s' % (SEGM_FMT(csr.u8), SEGM_FMT(dsr.u8), ADDR_FMT(sp.u16), ADDR_FMT(ip.u16)))

      self.init_states.append((csr, dsr, sp, ip, False))
      self.binaries.append((csr, dsr, sp, ip, symbols))

    import util

    breakpoints = breakpoints or []
    for bp in breakpoints:
      core, address = bp.split(',')
      util.CONSOLE.execute(['bp_add', core, address])

    # Storage
    from storage import STORAGES, StorageIOHandler

    self.storageio = StorageIOHandler(self)

    self.storages = {}
    storages = storages or []

    for storage_desc in storages:
      s_type, s_id, s_data = storage_desc.split(',')

      self.storages[s_id] = STORAGES[s_type](self, s_id, s_data)

    self.register_port(0x200, self.storageio)
    self.register_port(0x202, self.storageio)

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
    while self.keep_running:
      time.sleep(cpu.CPU_SLEEP_QUANTUM)

      for src in self.irq_sources:
        if not src:
          continue

        if not src.on_tick():
          continue

        self.message_bus.publish(bus.HandleIRQ(bus.ADDRESS_ANY, src))

      if len([_cpu for _cpu in self.cpus if _cpu.thread.is_alive()]) == 0:
        info('Machine halted')
        break

  def boot(self):
    for handler in self.ports:
      handler.boot()

    for storage in self.storages.values():
      storage.boot()

    self.for_each_cpu(lambda __cpu, machine: __cpu.boot(machine.init_states), self)

    info('Guest terminal available at %s' % self.conio.get_terminal_dev())

  def run(self):
    for handler in self.ports:
      handler.run()

    self.for_each_cpu(lambda __cpu: __cpu.run())

    self.thread = threading.Thread(target = self.loop, name = 'Machine')
    self.thread.start()

  def suspend(self):
    suspend_msg = bus.SuspendCore(bus.ADDRESS_ALL, audience = sum([len(_cpu.living_cores()) for _cpu in self.cpus]))
    self.message_bus.publish(suspend_msg)
    suspend_msg.wait()
    self.wake_up_all_event = suspend_msg.wake_up

  def wake_up(self):
    if not self.wake_up_all_event:
      return

    self.wake_up_all_event.set()
    self.wake_up_all_event = None

  def halt(self):
    halt_msg = bus.HaltCore(bus.ADDRESS_ALL, audience = sum([len(_cpu.living_cores()) for _cpu in self.cpus]))
    self.message_bus.publish(halt_msg)

    self.for_each_core(lambda __core: __core.wake_up())

    halt_msg.wait()

    for handler in self.ports:
      handler.halt()

    for storage in self.storages.values():
      storage.halt()

    if not self.thread:
      self.thread = threading.Thread(target = self.loop, name = 'Machine')

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

console.Console.register_command('halt', cmd_halt)
console.Console.register_command('boot', cmd_boot)
console.Console.register_command('run', cmd_run)
