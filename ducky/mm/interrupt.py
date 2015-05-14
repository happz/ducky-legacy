import enum

from ..cpu.registers import Registers
from ..irq.virtual import VirtualInterrupt, VIRTUAL_INTERRUPTS
from ..irq import InterruptList

class MMOperationList(enum.IntEnum):
  MPROTECT = 1

class MMInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('MMInterrupt: triggered')

    op = core.REG(Registers.R00).value

    if op == MMOperationList.MPROTECT:
      pass

    else:
      core.WARN('Unknown mm operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

VIRTUAL_INTERRUPTS[InterruptList.MM.value] = MMInterrupt
