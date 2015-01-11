import machine.bus
import irq

from threading2 import Thread

class Console(irq.IRQSource):
  def __init__(self, machine, conio, *args, **kwargs):
    super(Console, self).__init__(machine, *args, **kwargs)

    self.conio = conio
    self.thread = None

  def boot(self):
    super(Console, self).boot()

    self.thread = Thread(name = 'conio', target = self.loop, daemon = True, priority = 0.0)
    self.thread.start()

  def loop(self):
    while True:
      self.conio.read_raw_input()

      self.trigger()

