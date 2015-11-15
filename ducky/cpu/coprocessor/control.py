import enum

from ...interfaces import ISnapshotable
from ..import CPUException
from . import Coprocessor
from ...mm import SEGMENT_SHIFT
from ...errors import AccessViolationError
from ..instructions import InstructionSet, Inst_SIS, INSTRUCTION_SETS, InstDescriptor_Generic_Binary_R_R

from ctypes import c_ushort as u16

class ReadOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(ReadOnlyRegisterError, self).__init__('Register cr{:d} is read-only.'.format(r), *args, **kwargs)

class WriteOnlyRegisterError(CPUException):
  def __init__(self, r, *args, **kwargs):
    super(WriteOnlyRegisterError, self).__init__('Register cr{:d} is write-only.'.format(r), *args, **kwargs)

class ControlRegisters(enum.IntEnum):
  CR0 = 0  # CPUID
  CR1 = 1  # Interrupt Vector Table address
  CR2 = 2  # Interrupt Vector Table segment

class ControlCoprocessor(ISnapshotable, Coprocessor):
  def read_cr0(self):
    return u16((self.core.cpu.id << 8) | self.core.id)

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

    return getattr(self, handler)().value

  def write(self, r, value):
    if not self.core.privileged:
      raise AccessViolationError('It is not allowed to modify control registers in non-privileged mode')

    handler = 'write_cr%i' % r

    if not hasattr(self, handler):
      raise ReadOnlyRegisterError(r)

    return getattr(self, handler)(value)

#
# Instruction set
#
class ControlCoprocessorOpcodes(enum.IntEnum):
  """
  Control coprocessor instruction opcodes.
  """

  CTR = 0
  CTW = 1

  SIS = 63

class ControlCoprocessorInstructionSet(InstructionSet):
  instruction_set_id = 2

  opcodes = ControlCoprocessorOpcodes

class Inst_CTR(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'ctr'
  opcode = ControlCoprocessorOpcodes.CTR

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg1)
    core.registers.map[inst.reg1].value = core.control_coprocessor.read(inst.reg2)

class Inst_CTW(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'ctw'
  opcodes = ControlCoprocessorOpcodes.CTW

  @staticmethod
  def execute(core, inst):
    core.control_coprocessor.write(inst.reg1, core.registers.map[inst.reg2].value)

Inst_CTR(ControlCoprocessorInstructionSet)
Inst_CTW(ControlCoprocessorInstructionSet)
Inst_SIS(ControlCoprocessorInstructionSet)

ControlCoprocessorInstructionSet.init()
INSTRUCTION_SETS[ControlCoprocessorInstructionSet.instruction_set_id] = ControlCoprocessorInstructionSet
