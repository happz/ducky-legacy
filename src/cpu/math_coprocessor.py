import ctypes
import enum

from cpu.registers import Registers
from cpu.errors import CPUException
from mm import UInt32

class MathOperationList(enum.IntEnum):
  INCL  =  0
  DECL  =  1
  ADDL  =  2
  SUBL  =  3
  MULL  =  4
  DIVL  =  5
  MODL  =  6
  ITOL  =  7
  LTOI  =  8
  LTOII =  9
  IITOL = 10
  DUPL  = 11

class EmptyMathStackError(CPUException):
  def __init__(self):
    super(EmptyMathStackError, self).__init__('Math stack is empty')

class FullMathStackError(CPUException):
  def __init__(self):
    super(FullMathStackError, self).__init__('Math stack is full')

class RegisterSet(object):
  REGISTER_COUNT = 8

  def __init__(self):
    super(RegisterSet, self).__init__()

    self.stack = []

  def push(self, v):
    if len(self.stack) == self.REGISTER_COUNT:
      raise FullMathStackError()

    self.stack.append(v)

  def pop(self):
    if not self.stack:
      raise EmptyMathStackError()

    return self.stack.pop()

  def tos(self):
    if not self.stack:
      raise EmptyMathStackError()

    return self.stack[-1]

class MathCoprocessor(object):
  def __init__(self, core):
    super(MathCoprocessor, self).__init__()

    core.math_registers = RegisterSet()

from irq.virtual import VirtualInterrupt

class MathInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('MathInterrupt: triggered')

    op = core.REG(Registers.R00).u16
    core.REG(Registers.R00).u16 = 0

    if op == MathOperationList.ITOL:
      self.op_itol(core)

    elif op == MathOperationList.IITOL:
      self.op_iitol(core)

    elif op == MathOperationList.LTOI:
      self.op_ltoi(core)

    elif op == MathOperationList.LTOII:
      self.op_ltoii(core)

    elif op == MathOperationList.DUPL:
      self.op_dupl(core)

    elif op == MathOperationList.INCL:
      self.op_incl(core)

    elif op == MathOperationList.DECL:
      self.op_decl(core)

    elif op == MathOperationList.ADDL:
      self.op_addl(core)

    elif op == MathOperationList.SUBL:
      self.op_subl(core)

    elif op == MathOperationList.MULL:
      self.op_mull(core)

    elif op == MathOperationList.DIVL:
      self.op_divl(core)

    elif op == MathOperationList.MODL:
      self.op_modl(core)

    else:
      core.WARN('Unknown conio operation requested: %s', core.REG(Registers.R00))
      core.REG(Registers.R00).u16 = 0xFFFF

  def op_itol(self, core):
    lr = UInt32()
    r = core.REG(Registers.R01)

    lr.u32 = r.u16

    signed = ctypes.cast((ctypes.c_ushort * 1)(r.u16), ctypes.POINTER(ctypes.c_short)).contents.value
    if signed < 0:
      lr.u32 |= 0xFFFF0000

    core.math_registers.push(lr)

  def op_iitol(self, core):
    lr = UInt32()
    lr.u32 = core.REG(Registers.R01).u16 | (core.REG(Registers.R02).u16 << 16)
    core.math_registers.push(lr)

  def op_ltoi(self, core):
    lr = core.math_registers.pop()
    core.check_protected_reg(Registers.R01)
    core.REG(Registers.R01).u16 = lr.u32 & 0xFFFF

  def op_ltoii(self, core):
    lr = core.math_registers.pop()
    core.check_protected_reg(Registers.R01, Registers.R02)
    core.REG(Registers.R01).u16 =  lr.u32 & 0x0000FFFF
    core.REG(Registers.R02).u16 = (lr.u32 & 0xFFFF0000) >> 16

  def op_dupl(self, core):
    lr = core.math_registers.tos()
    core.math_registers.push(UInt32(lr.u32))

  def op_incl(self, core):
    core.math_registers.tos().u32 += 1

  def op_decl(self, core):
    core.math_registers.tos().u32 -= 1

  def op_addl(self, core):
    lr = core.math_registers.pop()
    core.math_registers.tos().u32 += lr.u32

  def op_subl(self, core, lr1, hr1, lr2, hr2):
    lr = core.math_registers.pop()
    core.math_registers.tos().u32 -= lr.u32

  def op_mull(self, core):
    lr = core.math_registers.pop()
    core.math_registers.tos().u32 *= lr.u32

  def op_divl(self, core):
    lr = core.math_registers.pop()
    core.math_registers.tos().u32 /= lr.u32

  def op_modl(self, core):
    lr = core.math_registers.pop()
    core.math_registers.tos().u32 %= lr.u32

from irq import InterruptList
from irq.virtual import VIRTUAL_INTERRUPTS

VIRTUAL_INTERRUPTS[InterruptList.MATH] = MathInterrupt
