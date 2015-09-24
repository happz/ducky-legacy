import enum

from ctypes import c_ushort, c_uint
from ..util import Flags

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

PROTECTED_REGISTERS = [
  Registers.FP,
  Registers.DS,
  Registers.CS,
  Registers.IP,
  Registers.FLAGS,
  Registers.CNT
]

GENERAL_REGISTERS   = [r for r in Registers if r.value < Registers.REGISTER_SPECIAL.value]
RESETABLE_REGISTERS = [r for r in Registers if r not in (Registers.FLAGS, Registers.REGISTER_SPECIAL, Registers.REGISTER_COUNT)]

REGISTER_NAMES = ['r{}'.format(r.value) for r in Registers if r.value < Registers.REGISTER_SPECIAL.value] + ['fp', 'sp', 'ds', 'cs', 'ip', 'flags', 'cnt']

class FlagsRegister(Flags):
  _fields_ = [
    ('privileged', c_ushort, 1),
    ('hwint',      c_ushort, 1),
    ('e',          c_ushort, 1),
    ('z',          c_ushort, 1),
    ('o',          c_ushort, 1),
    ('s',          c_ushort, 1)
  ]

  flag_labels = 'PHEZOS'

class RegisterSet(object):
  def __init__(self):
    super(RegisterSet, self).__init__()

    self.map = {}

    for register_name, register_id in zip(REGISTER_NAMES, Registers):
      if register_name == 'cnt':
        register_class = c_uint

      elif register_name == 'flags':
        register_class = FlagsRegister

      else:
        register_class = c_ushort

      register = register_class()

      setattr(self, register_name, register)
      self.map[register_name] = register
      self.map[register_id.value] = register
