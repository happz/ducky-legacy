import Queue
import time
import threading

import cpu
import mm

from cpu.errors import *
from util import *
from mm import SEGM_FMT, ADDR_FMT

import irq
import io.conio
import irq.timer
import irq.conio

class Machine(object):
  def __init__(self, cpus = 1, cores = 1, memory_size = None, binaries = None):
    super(Machine, self).__init__()

    binaries = binaries or []

    self.cpus = []
    self.memory = mm.MemoryController()
    self.ports = io.IOPortSet()
    self.irq_sources = irq.IRQSourceSet()

    self.queued_irqs = Queue.Queue()

    self.keep_running = True
    self.thread = None

    self.memory = mm.MemoryController()

    for cpuid in range(0, cpus):
      self.cpus.append(cpu.CPU(self, cpuid, cores = cores, memory_controller = self.memory))

    conio = io.conio.ConsoleIOHandler()
    self.register_port(0x100, conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console(0, conio))
    self.register_irq_source(irq.IRQList.TIMER, irq.timer.Timer(10))

    self.memory.boot()

    # Create simple testing IRQ handler for interrupt
    from mm import UInt8, UInt16, UInt24
    csr = UInt8(mm.SEGMENT_PROTECTED)
    dsr = UInt8(mm.SEGMENT_PROTECTED)
    interupt_counter_routine = cpu.SERVICE_ROUTINES['interrupt_counter']
    interupt_counter_routine.translate(self.memory)
    self.memory.load_text(csr, interupt_counter_routine.csb, interupt_counter_routine.cs)
    self.memory.load_data(dsr, interupt_counter_routine.dsb, interupt_counter_routine.ds)

    debug('set up timer interrupt vector')
    self.memory.write_u16(UInt24(self.memory.header.irq_table_address).u24 + 0, UInt16(csr.u8).u16, privileged = True)
    self.memory.write_u16(UInt24(self.memory.header.irq_table_address).u24 + 2, interupt_counter_routine.csb.u16, privileged = True)
    interupt_counter_routine.page.writable(True)

    self.init_states = []

    for _cpu in self.cpus:
      for _core in _cpu.cores:
        if len(binaries):
          csr, csb, dsr, dsb, sp = self.memory.load_file(binaries.pop(0))

        else:
          from mm import UInt8, UInt16

          # All service routines are located in the first segment
          csr = UInt8(mm.SEGMENT_PROTECTED)
          dsr = UInt8(mm.SEGMENT_PROTECTED)
          stack_page = self.memory.get_page(self.memory.alloc_page(segment = mm.SEGMENT_PROTECTED))
          sp = UInt16(stack_page.base_address + mm.PAGE_SIZE)

          routine = cpu.SERVICE_ROUTINES['idle_loop']
          routine.translate(self.memory)
 
          self.memory.load_text(csr, routine.csb, routine.cs)
          self.memory.load_data(dsr, routine.dsb, routine.ds)

          stack_page.readable(True)
          stack_page.writable(True)

          csb = routine.csb
          dsb = routine.dsb

        debug('init state: csr=%s, csb=%s, dsr=%s, dsb=%s, sp=%s'
           % (SEGM_FMT(csr.u8), ADDR_FMT(csb.u16), SEGM_FMT(dsr.u8), ADDR_FMT(dsb.u16), ADDR_FMT(sp.u16)))
        self.init_states.append((csr, csb, dsr, dsb, sp, False))

  def register_irq_source(self, irq, src, reassign = False):
    if self.irq_sources[irq]:
      if not reassign:
        raise InvalidResourceError('IRQ already assigned: %i' % irq)

      for i in range(0, len(self.irq_sources)):
        if not self.irq_sources[i]:
          irq = i
          break
      else:
        raise InvalidResourceError('IRQ already assigned, no available free IRQ: %i' % irq)

    self.irq_sources[irq] = src
    src.irq = irq
    return irq

  def unregister_irq_source(self, irq):
    self.irq_sources[irq] = None

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

        self.queued_irqs.put(src)

      if len([_cpu for _cpu in self.cpus if _cpu.thread.is_alive()]) == 0:
        info('Machine halted')
        break

  def boot(self):
    for _cpu in self.cpus:
      _cpu.boot(self.init_states)

    self.thread = threading.Thread(target = self.loop, name = 'Machine')
    self.thread.start()

  def halt(self):
    for _cpu in self.cpus:
      _cpu.halt()

