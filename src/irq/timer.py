import irq
import time

class Timer(irq.IRQSource):
  def __init__(self, *args, **kwargs):
    super(Timer, self).__init__(*args, **kwargs)

    self.thread = None
    self.profiler = profiler.STORE.get_machine_profiler()

  def boot(self):
    super(Timer, self).boot()

    self.thread = Thread(name = 'timer-irq', target = self.loop, daemon = True, priority = 0.0)
    self.thread.start()

  def loop(self):
    self.profiler.enable()

    while True:
      time.sleep(1)
      self.trigger()

    self.profiler.disable()
