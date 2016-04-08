import enum

from ...interfaces import ISnapshotable
from ..import CPUException
from . import Coprocessor
from ...errors import AccessViolationError
from ...mm import u32_t
from ...util import Flags

class ReadOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(ReadOnlyRegisterError, self).__init__('Register cr{:d} is read-only.'.format(r), *args, **kwargs)

class WriteOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(WriteOnlyRegisterError, self).__init__('Register cr{:d} is write-only.'.format(r), *args, **kwargs)

class ControlRegisters(enum.IntEnum):
  CR0 = 0  # CPUID
  CR1 = 1  # Interrupt Vector Table address
  CR2 = 2  # Page Table address
  CR3 = 3  # Flags

class CoreFlags(Flags):
  _flags = ['pt_enabled', 'jit']
  _labels = 'PJ'

class ControlCoprocessor(ISnapshotable, Coprocessor):
  def read_cr0(self):
    return u32_t((self.core.cpu.id << 16) | self.core.id).value

  def read_cr1(self):
    return u32_t(self.core.ivt_address).value

  def write_cr1(self, address):
    self.core.ivt_address = address

  def read_cr2(self):
    return u32_t(self.core.mmu.pt_address).value

  def write_cr2(self, address):
    self.core.mmu.pt_address = address

  def read_cr3(self):
    return CoreFlags.create(pt_enabled = self.core.mmu.pt_enabled, jit = self.core.cpu.machine.config.getbool('machine', 'jit', False)).to_int()

  def write_cr3(self, value):
    flags = CoreFlags.from_int(value)

    self.core.mmu.pt_enabled = flags.pt_enabled

  def read(self, r):
    if not self.core.privileged:
      raise AccessViolationError('It is not allowed to read control registers in non-privileged mode')

    handler = 'read_cr%i' % (r.value if isinstance(r, ControlRegisters) else r)

    if not hasattr(self, handler):
      raise WriteOnlyRegisterError(r)

    return getattr(self, handler)()

  def write(self, r, value):
    if not self.core.privileged:
      raise AccessViolationError('It is not allowed to modify control registers in non-privileged mode')

    handler = 'write_cr%i' % (r.value if isinstance(r, ControlRegisters) else r)

    if not hasattr(self, handler):
      raise ReadOnlyRegisterError(r)

    return getattr(self, handler)(value)
