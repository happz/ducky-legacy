import enum
import sys

import console
import irq
import util

from cpu.registers import Registers
from util import info, debug, warn

class VirtualInterrupt(object):
  def __init__(self, machine):
    super(VirtualInterrupt, self).__init__()

    self.machine = machine

  def run(self, core):
    pass

OPREG = lambda core: core.REG(Registers.R00)
REREG = lambda core: core.REG(Registers.R00)
P1REG = lambda core: core.REG(Registers.R01)

class VMDebugInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('VMDebugInterrupt: triggered')

    if OPREG(core).u16 == 0:
      util.CONSOLE.set_quiet_mode(True)

    else:
      util.CONSOLE.set_quiet_mode(False)

    REREG(core).u16 = 0

class ConioOperationList(enum.IntEnum):
  ECHO = 0

class ConioInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('ConioInterrupt: triggered')

    if OPREG(core).u16 == ConioOperationList.ECHO:
      core.cpu.machine.conio.echo = False if P1REG(core).u16 == 0 else True
      REREG(core).u16 = 0

    else:
      warn('Unknown conio operation requested: %s', UINT16_FMT(v))
      REREG(core).u16 = 0xFFFF

VIRTUAL_INTERRUPTS = {
  int(irq.InterruptList.VMDEBUG): VMDebugInterrupt,
  int(irq.InterruptList.CONIO):   ConioInterrupt,
}
