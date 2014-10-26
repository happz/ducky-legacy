import ctypes
import enum
import types

import mm

class Registers(enum.IntEnum):
  # 16 16bit registers available
  R00 =  0
  R01 =  1
  R02 =  2
  R03 =  3
  R04 =  4
  R05 =  5
  R06 =  6
  R07 =  7
  R08 =  8
  R09 =  9
  R10 = 10
  R11 = 11
  R12 = 12
  R13 = 13
  R14 = 14
  R15 = 15

  # Some registers have special meaning and/or usage
  CS    = 11 # Code Segment register
  DS    = 12 # Data Segment register
  FLAGS = 13 # Flags
  SP    = 14 # Stack pointer
  IP    = 15 # Instruction pointer

  # First special register
  REGISTER_SPECIAL = 11

  # How many registers do we have? This many...
  REGISTER_COUNT = 16

PROTECTED_REGISTERS = [
  11, 12, 13, 14, 15
]

RESETABLE_REGISTERS = [
  0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15
]

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
    ('eq',         ctypes.c_ubyte, 1),
    ('z',          ctypes.c_ubyte, 1),
    ('o',          ctypes.c_ubyte, 1),
    ('s',          ctypes.c_ubyte, 1)
  ]

class FlagsRegister(ctypes.Union):
  _pack_ = 0
  _fields_ = [
    ('u16', ctypes.c_ushort),
    ('flags', RealFlagsRegister)
  ]

class RegisterSet(object):
  registers = ['r%02i' % i for i in range(0, int(Registers.REGISTER_COUNT))]

  def __init__(self):
    super(RegisterSet, self).__init__()

    self.__register_map = []
    for register_name in self.registers:
      register_class = Register if register_name != 'r13' else FlagsRegister

      setattr(self, register_name, register_class())
      self.__register_map.append(getattr(self, register_name))

  def __len__(self):
    return Registers.REGISTER_COUNT

  def __getitem__(self, reg):
    if type(reg) == types.IntType:
      if reg < 0 or reg >= Registers.REGISTER_COUNT:
        raise IndexError('Unknown register index: %i' % reg)

      return self.__register_map[reg]

    if type(reg) == types.StringType:
      if reg not in self.registers:
        raise IndexError('unknown register name: %s' % reg)

      return getattr(self, reg)

    if type(reg) == Registers:
      return getattr(self, 'r%i' % reg)

    raise IndexError('Unknown register id: %s' % str(reg))

  def __setitem__(self, reg, value):
    self[reg].value = value

  def __iter__(self):
    return iter([getattr(self, reg) for reg in self.registers])

  cs    = property(lambda self: self[Registers.CS])
  ds    = property(lambda self: self[Registers.DS])
  flags = property(lambda self: self[Registers.FLAGS])
  sp    = property(lambda self: self[Registers.SP])
  ip    = property(lambda self: self[Registers.IP])

