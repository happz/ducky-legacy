from .. import irq
from .. import profiler

from threading import Thread

class Console(irq.IRQSource):
  def __init__(self, machine, conio, *args, **kwargs):
    super(Console, self).__init__(machine, *args, **kwargs)

    self.conio = conio
    self.thread = None

    self.profiler = profiler.STORE.get_machine_profiler()

  def boot(self):
    super(Console, self).boot()

    self.thread = Thread(name = 'conio', target = self.loop)
    self.thread.daemon = True
    self.thread.start()

  def loop(self):
    self.profiler.enable()

    while True:
      if self.conio.read_raw_input() is False:
        break

      self.machine.trigger_irq(self)

    self.profiler.disable()
