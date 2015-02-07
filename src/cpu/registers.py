import ctypes
import enum
import types

import mm

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
  FP    = 13 # Frame Pointer
  SP    = 14 # Stack Pointer
  DS    = 15 # Data Segment Register
  CS    = 16 # Code Segment register
  IP    = 17 # Instruction pointer
  FLAGS = 18 # Flags

  # First special register
  REGISTER_SPECIAL = 13

  # How many registers do we have? This many...
  REGISTER_COUNT = 19

PROTECTED_REGISTERS = range(Registers.REGISTER_SPECIAL, Registers.REGISTER_COUNT)

RESETABLE_REGISTERS = [i for i in range(0, Registers.REGISTER_COUNT) if i != Registers.FLAGS]

REGISTER_NAMES = ['r%i' % i for i in range(0, Registers.REGISTER_SPECIAL)] + ['fp', 'sp', 'ds', 'cs', 'ip', 'flags']

class Register(mm.UInt16):
  pass

class RealFlagsRegister(ctypes.LittleEndianStructure):
  PRIVILEGED_ENABLED = 0
  HWINT_ENABLED      = 1
  EQ                 = 2

  _pack_ = 0
  _fields_ = [
    ('privileged', ctypes.c_ubyte, 1),
    ('hwint',      ctypes.c_ubyte, 1),
    ('e',          ctypes.c_ubyte, 1),
    ('z',          ctypes.c_ubyte, 1),
    ('o',          ctypes.c_ubyte, 1),
    ('s',          ctypes.c_ubyte, 1)
  ]

  def __repr__(self):
    return '<RealFlagsRegister: privileged=%i, hwint=%i, e=%i, z=%i, o=%i, s=%i>' % (self.privileged, self.hwint, self.e, self.z, self.o, self.s)

class FlagsRegister(ctypes.Union):
  _pack_ = 0
  _fields_ = [
    ('u16', ctypes.c_ushort),
    ('flags', RealFlagsRegister)
  ]

class RegisterSet(object):
  def __init__(self):
    super(RegisterSet, self).__init__()

    self.map = {}

    for register_name, register_id in zip(REGISTER_NAMES, Registers):
      if not register_name:
        break

      register_class = Register if register_name != 'flags' else FlagsRegister

      register = register_class()

      setattr(self, register_name, register)
      self.map[register_name] = register
      self.map[register_id.value] = register
