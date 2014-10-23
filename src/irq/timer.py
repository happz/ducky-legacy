import irq

class Timer(irq.IRQSource):
  def __init__(self, batch, *args, **kwargs):
    super(Timer, self).__init__(*args, **kwargs)

    self.steps = 0
    self.batch = batch

  def on_tick(self):
    self.steps += 1

    if self.steps < self.batch:
      return False

    self.steps = 0
    return True
