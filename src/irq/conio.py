import select
import sys

import irq

class Console(irq.IRQSource):
  def __init__(self, batch, io, *args, **kwargs):
    super(Console, self).__init__(*args, **kwargs)

    self.steps = 0
    self.batch = batch
    self.io = io

  def on_tick(self):
    self.steps += 1

    if self.steps < self.batch:
      return False

    self.steps = 0

    if sys.stdin not in select.select([sys.stdin], [], [], 0)[0]:
      return False

    line = sys.stdin.readline()
    if not line:
      # stdin closed, wtf?
      return False

    self.io.add_to_buffer(line + '\n')

    return True
