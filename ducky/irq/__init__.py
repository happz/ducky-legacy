import enum

from .. import machine
from .. import reactor

class IRQList(enum.IntEnum):
  TIMER = 0
  CONIO = 1

  IRQ_COUNT = 16

class InterruptList(enum.IntEnum):
  HALT    = 0
  BLOCKIO = 1
  VMDEBUG = 2
  CONIO   = 3
  MM      = 4
  MATH    = 5

  INT_COUNT = 64

class TimerIRQEvent(reactor.ReactorTask):
  def __init__(self, machine, handler):
    self.machine = machine
    self.handler = handler

  def runnable(self):
    return True

  def run(self):
    machine.route_irq(self.handler)

class IRQSource(machine.MachineWorker):
  def __init__(self, machine):
    super(IRQSource, self).__init__()

    self.machine = machine

    self.irq = None
    self.is_maskable = True

  def boot(self):
    pass

class IRQSourceSet(object):
  def __init__(self):
    super(IRQSourceSet, self).__init__()

    self.__sources = [None for _ in range(0, IRQList.IRQ_COUNT)]

  def __check_irq_limits(self, irq):
    if irq < 0 or irq >= IRQList.IRQ_COUNT:
      raise IndexError('IRQ out of range: irq=%i' % irq)

  def __getitem__(self, irq):
    self.__check_irq_limits(irq)
    return self.__sources[irq]

  def __setitem__(self, irq, source):
    self.__check_irq_limits(irq)
    self.__sources[irq] = source

  def __delitem__(self, irq):
    self.__check_irq_limits(irq)
    self.__sources[irq] = None

  def __iter__(self):
    return iter(self.__sources)

  def ihandlers(self):
    return self.__sources.itervalues()

  def __len__(self):
    return len(self.__sources)

  def __contains__(self, irq):
    self.__check_irq_limits(irq)
    return self.__sources is not None
