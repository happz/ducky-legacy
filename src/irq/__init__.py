import enum

import machine.bus

from threading2 import Lock

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

class IRQSource(object):
  def __init__(self, machine):
    super(IRQSource, self).__init__()

    self.machine = machine

    self.lock = Lock()
    self.triggered = 0

    self.irq = None
    self.is_maskable = True

  def trigger(self):
    with self.lock:
      self.triggered += 1

      if self.triggered == 1:
        self.machine.message_bus.publish(machine.bus.HandleIRQ(machine.bus.ADDRESS_ANY, self))

  def clear(self):
    with self.lock:
      self.triggered = 0

  def boot(self):
    pass

  def halt(self):
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

  def __len__(self):
    return len(self.__sources)

  def __contains__(self, irq):
    self.__check_irq_limits(irq)
    return self.__sources != None
