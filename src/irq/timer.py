import irq

class Timer(irq.IRQSource):
  def __init__(self, cpu, batch, *args, **kwargs):
    super(Timer, self).__init__(cpu, *args, **kwargs)

    self.steps = 0
    self.batch = batch

    self.irq = self.cpu.register_irq_source(irq.IRQList.TIMER, self)

  def on_tick(self):
    self.steps += 1

    if self.steps < self.batch:
      return False

    self.steps = 0
    return True
