import time
import threading

import cpu
import mm
from cpu.errors import *
from util import *

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

    self.keep_running = True
    self.thread = None

    self.memory = mm.MemoryController()

    for cpuid in range(0, cpus):
      self.cpus.append(cpu.CPU(self, cpuid, cores = cores, memory_controller = self.memory))

    conio = io.conio.ConsoleIOHandler()
    self.register_port(0x100, conio)

    self.register_irq_source(irq.IRQList.CONIO, irq.conio.Console(0, conio))
    self.register_irq_source(irq.IRQList.TIMER, irq.timer.Timer(50))

    self.memory.boot()

    self.init_states = []

    for _cpu in self.cpus:
     for _core in _cpu.cores:
       if len(binaries):
         csr, csb, dsr, dsb, sp = self.memory.load_file(binaries[0])
         
       else:
         from mm import UInt16
         
         # All service routines are located in the first segment
         csr = UInt16(0)
         dsr = UInt16(0)
         service_page = self.memory.get_page(self.memory.alloc_page(0))
 
         csb = UInt16(service_page.base_address)
         dsb = UInt16(service_page.base_address + mm.PAGE_SIZE / 2)
 
         csb, cs, dsb, ds = cpu.get_service_routine('halt', csb, dsb)
 
         sp = UInt16(service_page.base_address + mm.PAGE_SIZE)
 
         self.memory.load_text(csr, csb, cs)
         self.memory.load_data(dsr, dsb, ds)
 
       debug('init state: csr=0x%X, csb=0x%X, dsr=0x%X, dsb=0x%X, sp=0x%X' % (csr.u16, csb.u16, dsr.u16, dsb.u16, sp.u16))
 
       self.init_states.append((csr, csb, dsr, dsb, sp, True))

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

        for _cpu in self.cpus:
          for _core in _cpu.cores:
            if not _core.idle:
              continue
            _core.irq_queue.put(src)
            break
          else:
            self.cpus[0].cores[0].irq_queue.put(src)

      if len([_cpu for _cpu in self.cpus if _cpu.thread.is_alive()]) == 0:
        info('Machine halt!')
        break

  def boot(self):
    for _cpu in self.cpus:
      _cpu.boot(self.init_states)

    self.thread = threading.Thread(target = self.loop, name = 'Machine')
    self.thread.start()

