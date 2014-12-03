import enum

class IRQList(enum.IntEnum):
  TIMER = 0
  CONIO = 1

  IRQ_COUNT = 16

class IRQSource(object):
  def __init__(self):
    super(IRQSource, self).__init__()

    self.irq = None
    self.is_maskable = True

  def boot(self):
    pass

  def halt(self):
    pass

  def on_tick(self):
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
