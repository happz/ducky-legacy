import enum
import logging

from ...interfaces import ISnapshotable
from ...errors import RegisterAccessError
from . import Coprocessor
from ...util import Flags

class ControlRegisters(enum.IntEnum):
  CR0 = 0  # CPUID
  CR1 = 1  # Interrupt Vector Table address
  CR2 = 2  # Page Table address
  CR3 = 3  # Flags

CONTROL_FLAG_PT_ENABLED = 0x00000001
CONTROL_FLAG_JIT        = 0x00000002
CONTROL_FLAG_VMDEBUG    = 0x00000004

class CoreFlags(Flags):
  _flags = ['pt_enabled', 'jit', 'vmdebug']
  _labels = 'PJV'

class ControlCoprocessor(ISnapshotable, Coprocessor):
  def read_cr0(self):
    return ((self.core.cpu.id << 16) | self.core.id) & 0xFFFFFFFF

  def read_cr1(self):
    return self.core.evt_address & 0xFFFFFFFF

  def write_cr1(self, address):
    self.core.evt_address = address

  def read_cr2(self):
    return self.core.mmu.pt_address & 0xFFFFFFFF

  def write_cr2(self, address):
    self.core.mmu.pt_address = address

  def read_cr3(self):
    return CoreFlags.create(pt_enabled = self.core.mmu.pt_enabled,
                            jit = self.core.cpu.machine.config.getbool('machine', 'jit', False),
                            vmdebug = self.core.LOGGER.getEffectiveLevel() == logging.DEBUG).to_int()

  def write_cr3(self, value):
    flags = CoreFlags.from_int(value)

    self.core.mmu.pt_enabled = flags.pt_enabled

    if flags.vmdebug is True:
      self.core.LOGGER.setLevel(logging.DEBUG)

    else:
      self.core.LOGGER.setLevel(logging.INFO)

  def read(self, r):
    if not self.core.privileged:
      raise RegisterAccessError('read', r)

    handler = 'read_cr%i' % (r.value if isinstance(r, ControlRegisters) else r)

    if not hasattr(self, handler):
      raise RegisterAccessError('read', r)

    return getattr(self, handler)()

  def write(self, r, value):
    if not self.core.privileged:
      raise RegisterAccessError('write', r)

    handler = 'write_cr%i' % (r.value if isinstance(r, ControlRegisters) else r)

    if not hasattr(self, handler):
      raise RegisterAccessError('write', r)

    return getattr(self, handler)(value)
