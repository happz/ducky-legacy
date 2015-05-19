class VirtualInterrupt(object):
  def __init__(self, machine):
    super(VirtualInterrupt, self).__init__()

    self.machine = machine

  def run(self, core):
    pass

VIRTUAL_INTERRUPTS = {}

from ..mm import interrupt  # noqa - it's not unused, after import mm interrupt handler registers itself
