import time

from .. import irq

from ..interfaces import IReactorTask

TIMER_FREQ = 100.0

class TimerIRQTask(IReactorTask):
  def __init__(self, machine, timer_irq):
    self.machine = machine
    self.timer_irq = timer_irq

    self.stamp = 0
    self.counter = 0
    self.round = 0

    self.tick = 1.0 / TIMER_FREQ

  def runnable(self):
    return True

  def run(self):
    self.counter += 1

    if self.counter < 100:
      return

    self.counter = 0

    stamp = time.time()
    diff = stamp - self.stamp
    if diff < self.tick:
      return

    self.stamp = stamp
    self.round += 1

    self.machine.trigger_irq(self.timer_irq)

class TimerIRQ(irq.IRQSource):
  def __init__(self, machine, *args, **kwargs):
    super(TimerIRQ, self).__init__(machine, *args, **kwargs)

    self.timer_task = TimerIRQTask(machine, self)

  def boot(self):
    self.machine.reactor.add_task(self.timer_task)

  def halt(self):
    self.machine.reactor.remove_task(self.timer_task)
