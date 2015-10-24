import enum

from ...interfaces import ISnapshotable
from ..import CPUException
from . import Coprocessor
from ...mm import SEGMENT_SHIFT
from ...errors import AccessViolationError

from ctypes import c_ushort as u16

class ReadOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(ReadOnlyRegisterError, self).__init__('Register cr{:i} is read-only.'.format(r), *args, **kwargs)

class WriteOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(WriteOnlyRegisterError, self).__init__('Register cr{:i} is write-only.'.format(r), *args, **kwargs)

class ControlRegisters(enum.IntEnum):
  CR0 = 0  # System ID (reserved)
  CR1 = 1  # Interrupt Vector Table address
  CR2 = 2  # Interrupt Vector Table segment

class MathCoprocessor(ISnapshotable, Coprocessor):
  def read_cr0(self):
    return u16(0)

  def write_cr0(self, value):
    raise ReadOnlyRegisterError('cr0')

  def read_cr1(self):
    return u16(self.core.ivt_address & 0xFFFF)

  def write_cr1(self, address):
    self.core.ivt_address = (self.core.ivt_address & 0xFF0000) | address

  def read_cr2(self):
    return u16((self.core.ivt_address >> SEGMENT_SHIFT) & 0xFF)

  def write_cr2(self, segment):
    self.core.ivt_address = (self.core.ivt_address & 0x00FFFF) | ((segment & 0xFF) << SEGMENT_SHIFT)

  def read(self, r):
    if not self.core.privileged:
      raise AccessViolationError('It is not allowed to read control registers in non-privileged mode')

    handler = 'read_cr%i' % r

    if not hasattr(self, handler):
      raise WriteOnlyRegisterError(r)

    return getattr(self, handler)()

  def write(self, r, value):
    if not self.core.privileged:
      raise AccessViolationError('It is not allowed to modify control registers in non-privileged mode')

    handler = 'write_cr%i' % r

    if not hasattr(self, handler):
      raise ReadOnlyRegisterError(r)

    return getattr(self, handler)(value)
