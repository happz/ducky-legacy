import enum
import sys

import console
import irq
import mm
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
P2REG = lambda core: core.REG(Registers.R02)

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

class MMOperationList(enum.IntEnum):
  ALLOC_PAGES = 0
  FREE_PAGES  = 1
  MMAP_AREA   = 2
  UNMMAP_AREA = 3
  GET_PAGE    = 4

class MMInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('MMInterrupt: triggered')

    if OPREG(core).u16 == MMOperationList.ALLOC_PAGES:
      segment = mm.UInt8(core.registers.ds.u16 & 0xFF)
      count = P1REG(core).u16

      pages = core.memory.alloc_pages(segment = segment, count = count)

      if pages == None:
        REREG(core).u16 = 0xFFFF

      else:
        REREG(core).u16 = pages[0].segment_address

    elif OPREG(core).u16 == MMOperationList.FREE_PAGES:
      page = core.memory.get_page(mm.addr_to_page(mm.segment_addr_to_addr(core.registers.cs.u16, P1REG(core).u16)))
      count = P2REG(core).u16

      core.memory.free_pages(page, count = count)

      REREG(core).u16 = 0

    elif OPREG(core).u16 == MMOperationList.GET_PAGE:
      page = mm.addr_to_page(mm.segment_addr_to_addr(core.registers.cs.u16, P1REG(core).u16))

      page = core.memory.alloc_specific_page(page)

      if not page:
        REREG(core).u16 = 0xFFFF

      else:
        REREG(core).u16 = page.segment_address

VIRTUAL_INTERRUPTS = {
  irq.InterruptList.VMDEBUG.value: VMDebugInterrupt,
  irq.InterruptList.CONIO.value:   ConioInterrupt,
  irq.InterruptList.MM.value:      MMInterrupt
}
