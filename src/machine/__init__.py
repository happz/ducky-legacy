import Queue
import sys
import time
import threading

import cpu
import mm
import machine.bus

from cpu.errors import InvalidResourceError
from util import debug, info
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT

import irq
import io_handlers

class Machine(object):
  def __init__(self, cpus = 1, cores = 1, memory_size = None, binaries = None, irq_routines = None):
    super(Machine, self).__init__()

    self.nr_cpus = cpus
    self.nr_cores = cores

    binaries = binaries or []

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

    conio = io_handlers.conio.ConsoleIOHandler()
    self.register_port(0x100, conio)
    self.register_port(0x101, conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console())
    self.register_irq_source(irq.IRQList.TIMER, irq.timer.Timer(10))

    self.memory.boot()

    if irq_routines:
      info('Loading IRQ routines from file %s' % irq_routines)

      from mm import UInt8, UInt16, UInt24

      csr, dsr, sp, ip, symbols = self.memory.load_file(irq_routines)

      desc = cpu.InterruptVector()
      desc.cs = csr.u8
      desc.ds = dsr.u8

      # Timer IRQ
      desc.ip = symbols['irq_timer'].u16
      self.memory.save_interrupt_vector(self.memory.irq_table_address, 0, desc)

      # Halt interrupt
      desc.ip = symbols['int_halt'].u16
      self.memory.save_interrupt_vector(self.memory.int_table_address, 0, desc)

    self.init_states = []

    for bc_file in binaries:
      csr, dsr, sp, ip, symbols = self.memory.load_file(bc_file)

      debug('init state: csr=%s, dsr=%s, sp=%s, ip=%s' % (SEGM_FMT(csr.u8), SEGM_FMT(dsr.u8), ADDR_FMT(sp.u16), ADDR_FMT(ip.u16)))

      self.init_states.append((csr, dsr, sp, ip, False))

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

    for _cpu in self.cpus:
      _cpu.boot(self.init_states)

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
    for handler in self.ports:
      handler.halt()

    halt_msg = bus.HaltCore(bus.ADDRESS_ALL, audience = sum([len(_cpu.living_cores()) for _cpu in self.cpus]))
    self.message_bus.publish(halt_msg)
    halt_msg.wait()

