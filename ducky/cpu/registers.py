import ctypes
import enum

class Flags(enum.IntEnum):
  PRIVILEGED = 0x01
  HWINT      = 0x02
  EQUAL      = 0x04
  ZERO       = 0x08
  OVERFLOW   = 0x10
  SIGNED     = 0x20

class Registers(enum.IntEnum):
  # 16 16bit registers available
  R00   =  0
  R01   =  1
  R02   =  2
  R03   =  3
  R04   =  4
  R05   =  5
  R06   =  6
  R07   =  7
  R08   =  8
  R09   =  9
  R10   = 10
  R11   = 11
  R12   = 12

  # Some registers have special meaning and/or usage
  FP    = 13  # Frame Pointer
  SP    = 14  # Stack Pointer
  DS    = 15  # Data Segment Register
  CS    = 16  # Code Segment register
  IP    = 17  # Instruction pointer
  FLAGS = 18  # Flags
  CNT   = 19  # Instruction counter

  # First special register
  REGISTER_SPECIAL = 13

  # How many registers do we have? This many...
  REGISTER_COUNT = 20

PROTECTED_REGISTERS = [13, 15, 16, 17, 18, 19]

RESETABLE_REGISTERS = [i for i in range(0, Registers.REGISTER_COUNT) if i != Registers.FLAGS]

REGISTER_NAMES = ['r%i' % i for i in range(0, Registers.REGISTER_SPECIAL)] + ['fp', 'sp', 'ds', 'cs', 'ip', 'flags', 'cnt']

class FlagsRegister(object):
  def __init__(self):
    self.privileged = 0
    self.hwint = 1
    self.e = 0
    self.z = 0
    self.o = 0
    self.s = 0

  def to_uint16(self):
    return self.privileged | self.hwint << 1 | self.e << 2 | self.z << 3 | self.o << 4 | self.s << 5

  def from_uint16(self, u):
    self.privileged = 1 if u & Flags.PRIVILEGED else 0
    self.hwint = 1 if u & Flags.HWINT else 0
    self.e = 1 if u & Flags.EQUAL else 0
    self.z = 1 if u & Flags.ZERO else 0
    self.o = 1 if u & Flags.OVERFLOW else 0
    self.s = 1 if u & Flags.SIGNED else 0

  def __repr__(self):
    return '<FlagsRegister: privileged=%i, hwint=%i, e=%i, z=%i, o=%i, s=%i>' % (self.privileged, self.hwint, self.e, self.z, self.o, self.s)

class RegisterSet(object):
  def __init__(self):
    super(RegisterSet, self).__init__()

    self.map = {}

    for register_name, register_id in zip(REGISTER_NAMES, Registers):
      if not register_name:
        break

      register_class = ctypes.c_ushort if register_name != 'flags' else FlagsRegister

      register = register_class()

      setattr(self, register_name, register)
      self.map[register_name] = register
      self.map[register_id.value] = register
