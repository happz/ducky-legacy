import enum

from .. import irq
from .. import mm
from .. import util

from ..cpu.registers import Registers

class VirtualInterrupt(object):
  def __init__(self, machine):
    super(VirtualInterrupt, self).__init__()

    self.machine = machine

  def run(self, core):
    pass

def OPREG(core):
  return core.REG(Registers.R00)

def REREG(core):
  return core.REG(Registers.R00)

def P1REG(core):
  return core.REG(Registers.R01)

def P2REG(core):
  return core.REG(Registers.R02)

class VMDebugOperationList(enum.Enum):
  QUIET_MODE = 0

class VMDebugInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('VMDebugInterrupt: triggered')

    op = core.REG(Registers.R00).value
    core.REG(Registers.R00).value = 0

    if op == VMDebugOperationList.QUIET_MODE.value:
      core.DEBUG('setting quiet mode to %s', core.REG(Registers.R01).value)
      util.CONSOLE.set_quiet_mode(False if core.REG(Registers.R01).value == 0 else True)

    else:
      core.WARN('Unknown vmdebug operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

class MMOperationList(enum.IntEnum):
  ALLOC_PAGES = 0
  FREE_PAGES  = 1
  MMAP_AREA   = 2
  UNMMAP_AREA = 3
  GET_PAGE    = 4

class MMInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('MMInterrupt: triggered')

    if OPREG(core).value == MMOperationList.ALLOC_PAGES:
      segment = mm.UInt8(core.registers.ds.value & 0xFF)
      count = P1REG(core).value

      pages = core.memory.alloc_pages(segment = segment, count = count)

      if pages is None:
        REREG(core).value = 0xFFFF

      else:
        REREG(core).value = pages[0].segment_address

    elif OPREG(core).value == MMOperationList.FREE_PAGES:
      page = core.memory.get_page(mm.addr_to_page(mm.segment_addr_to_addr(core.registers.cs.value, P1REG(core).value)))
      count = P2REG(core).value

      core.memory.free_pages(page, count = count)

      REREG(core).value = 0

    elif OPREG(core).value == MMOperationList.GET_PAGE:
      page = mm.addr_to_page(mm.segment_addr_to_addr(core.registers.cs.value, P1REG(core).value))

      page = core.memory.alloc_specific_page(page)

      if not page:
        REREG(core).value = 0xFFFF

      else:
        REREG(core).value = page.segment_address

VIRTUAL_INTERRUPTS = {
  irq.InterruptList.VMDEBUG.value: VMDebugInterrupt,
  irq.InterruptList.MM.value:      MMInterrupt
}
