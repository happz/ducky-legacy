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
  FLAGS = 17 # Flags
  IP    = 18 # Instruction pointer

  # First special register
  REGISTER_SPECIAL = 13

  # How many registers do we have? This many...
  REGISTER_COUNT = 19

PROTECTED_REGISTERS = range(Registers.REGISTER_SPECIAL, Registers.REGISTER_COUNT)

RESETABLE_REGISTERS = [i for i in range(0, Registers.REGISTER_COUNT) if i != Registers.FLAGS]

REGISTER_NAMES = ['r%i' % i for i in range(0, Registers.REGISTER_SPECIAL)] + ['fp', 'sp', 'ds', 'cs', 'flags', 'ip']

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

class FlagsRegister(ctypes.Union):
  _pack_ = 0
  _fields_ = [
    ('u16', ctypes.c_ushort),
    ('flags', RealFlagsRegister)
  ]

class RegisterSet(object):
  def __init__(self):
    super(RegisterSet, self).__init__()

    self.__map_id   = {}
    self.__map_name = {}
    self.__map_list = []

    for register_name, register_id in zip(REGISTER_NAMES, Registers):
      if not register_name:
        break

      register_class = Register if register_name != 'flags' else FlagsRegister

      register = register_class()

      setattr(self, register_name, register)
      self.__map_name[register_name] = register
      self.__map_id[register_id] = register
      self.__map_list.append(register)

  def __len__(self):
    return Registers.REGISTER_COUNT

  def __getitem__(self, reg):
    if type(reg) in (types.IntType, types.LongType):
      if reg < 0 or reg >= Registers.REGISTER_COUNT:
        raise IndexError('Unknown register index: %i' % reg)

      return self.__map_list[reg]

    if type(reg) == types.StringType:
      if reg not in REGISTER_NAMES:
        raise IndexError('unknown register name: %s' % reg)

      return self.__map_name[reg]

    if type(reg) == Registers:
      return self.__map_id[reg]

    raise IndexError('Unknown register id: %s' % str(reg))

  def __setitem__(self, reg, value):
    self[reg].value = value

  def __iter__(self):
    return iter([getattr(self, reg) for reg in REGISTER_NAMES])

