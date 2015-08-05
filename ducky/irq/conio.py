from .. import irq

from ..interfaces import IReactorTask

class ConioIRQTask(IReactorTask):
  def __init__(self, machine, conio_io, conio_irq):
    self.machine = machine
    self.conio_io = conio_io
    self.conio_irq = conio_irq

  def runnable(self):
    return True

  def run(self):
    self.conio_io.read_raw_input(self.conio_irq)

class ConsoleIRQ(irq.IRQSource):
  def __init__(self, machine, conio_io, *args, **kwargs):
    super(ConsoleIRQ, self).__init__(machine, *args, **kwargs)

    self.conio_task = ConioIRQTask(machine, conio_io, self)

  def boot(self):
    self.machine.reactor.add_task(self.conio_task)

  def halt(self):
    self.machine.reactor.remove_task(self.conio_task)
