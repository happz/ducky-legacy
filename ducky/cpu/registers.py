import enum

class Registers(enum.IntEnum):
  # General purpose registers
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
  R13   = 13
  R14   = 14
  R15   = 15
  R16   = 16
  R17   = 17
  R18   = 18
  R19   = 19
  R20   = 20
  R21   = 21
  R22   = 22
  R23   = 23
  R24   = 24
  R25   = 25
  R26   = 26
  R27   = 27
  R28   = 28
  R29   = 29

  # Special registers
  FP    = 30  # Frame Pointer
  SP    = 31  # Stack Pointer

  # Inaccessible registers
  IP    = 32  # Instruction pointer
  CNT   = 33  # Instruction counter

  # First special register
  REGISTER_SPECIAL = 30

  # How many registers do we have? This many...
  REGISTER_COUNT = 34

PROTECTED_REGISTERS = [
  Registers.FP,
  Registers.IP,
  Registers.CNT
]

FLAGS = Registers.REGISTER_COUNT.value + 100

GENERAL_REGISTERS   = [r for r in Registers if r.value < Registers.REGISTER_SPECIAL.value]
RESETABLE_REGISTERS = [r for r in Registers if r.value < Registers.IP]

REGISTER_NAMES = ['r{}'.format(r.value) for r in Registers if r.value < Registers.REGISTER_SPECIAL.value] + ['fp', 'sp', 'ip', 'cnt']

class RegisterSet(list):
  def __init__(self):
    super(RegisterSet, self).__init__()

    for reg_name in REGISTER_NAMES:
      self.append(0)
