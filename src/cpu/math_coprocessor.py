import ctypes
import enum

from cpu.registers import Registers
from mm import i16, u16, u32, i32, UINT32_FMT, UINT16_FMT
from irq import InterruptList
from irq.virtual import VIRTUAL_INTERRUPTS, VirtualInterrupt

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
  UTOL  = 12
  SYMDIVL = 13
  SYMMODL = 14

class EmptyMathStackError(Exception):
  def __init__(self):
    super(EmptyMathStackError, self).__init__('Math stack is empty')

class FullMathStackError(Exception):
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

class MathInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('MathInterrupt: triggered')

    op = core.REG(Registers.R00).value
    core.REG(Registers.R00).value = 0

    if op == MathOperationList.ITOL:
      self.op_itol(core)

    elif op == MathOperationList.UTOL:
      self.op_utol(core)

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

    elif op == MathOperationList.SYMDIVL:
      self.op_symdivl(core)

    elif op == MathOperationList.SYMMODL:
      self.op_symmodl(core)

    else:
      core.WARN('Unknown math operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

  def dump_stack(self, core):
    core.DEBUG('Math stack:')
    for index, lr in enumerate(core.math_registers.stack):
      core.DEBUG('#%02i: %s', index, UINT32_FMT(lr))
    core.DEBUG('---')

  def op_itol(self, core):
    r = core.REG(Registers.R01)
    lr = u32(r.value)

    signed = ctypes.cast((u16 * 1)(r), ctypes.POINTER(i16)).contents.value
    if signed < 0:
      lr.value |= 0xFFFF0000

    core.math_registers.push(lr)

    core.DEBUG('itol: i=%s', UINT16_FMT(core.REG(Registers.R01).value))
    self.dump_stack(core)

  def op_utol(self, core):
    r = core.REG(Registers.R01)
    lr = u32(r.value)

    core.math_registers.push(lr)

    core.DEBUG('utol: i=%s', UINT16_FMT(core.REG(Registers.R01).value))
    self.dump_stack(core)

  def op_iitol(self, core):
    lr = u32(core.REG(Registers.R01).value | (core.REG(Registers.R02).value << 16))

    core.math_registers.push(lr)

    core.DEBUG('iitol: lb=%s, hb=%s', UINT16_FMT(core.REG(Registers.R01).value), UINT16_FMT(core.REG(Registers.R02).value))
    self.dump_stack(core)

  def op_ltoi(self, core):
    lr = core.math_registers.pop()

    core.check_protected_reg(Registers.R01)
    core.REG(Registers.R01).value = lr.value & 0xFFFF

    core.DEBUG('ltoi: i=%s', UINT16_FMT(core.REG(Registers.R01).value))
    self.dump_stack(core)

  def op_ltoii(self, core):
    lr = core.math_registers.pop()

    core.check_protected_reg(Registers.R01, Registers.R02)
    core.REG(Registers.R01).value =  lr.value & 0x0000FFFF
    core.REG(Registers.R02).value = (lr.value & 0xFFFF0000) >> 16

    core.DEBUG('ltoii: lb=%s, hb=%s', UINT16_FMT(core.REG(Registers.R01).value), UINT16_FMT(core.REG(Registers.R02).value))
    self.dump_stack(core)

  def op_dupl(self, core):
    lr = core.math_registers.tos()

    core.math_registers.push(u32(lr.value))

    core.DEBUG('dupl:')
    self.dump_stack(core)

  def op_incl(self, core):
    core.math_registers.tos().value += 1

  def op_decl(self, core):
    core.math_registers.tos().value -= 1

  def op_addl(self, core):
    lr = core.math_registers.pop()

    core.math_registers.tos().value += lr.value

  def op_subl(self, core, lr1, hr1, lr2, hr2):
    lr = core.math_registers.pop()

    core.math_registers.tos().value -= lr.value

  def op_mull(self, core):
    lr = core.math_registers.pop()
    old_tos = core.math_registers.tos().value

    core.math_registers.tos().value *= lr.value

    core.DEBUG('mull: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr))
    self.dump_stack(core)

  def op_divl(self, core):
    core.DEBUG('divl:')

    lr = core.math_registers.pop()
    old_tos = core.math_registers.tos().value
    tos = core.math_registers.tos()

    i = ctypes.cast((u32 * 1)(tos), ctypes.POINTER(i32)).contents.value
    j = ctypes.cast((u32 * 1)(lr),  ctypes.POINTER(i32)).contents.value
    core.DEBUG('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i /= j
    core.DEBUG('  i=%i (%s)', i, type(i))
    tos.value = i

    core.DEBUG('divl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr))
    self.dump_stack(core)

  def op_symdivl(self, core):
    core.DEBUG('symdivl:')

    lr = core.math_registers.pop()
    old_tos = core.math_registers.tos().value
    tos = core.math_registers.tos()

    i = ctypes.cast((u32 * 1)(tos), ctypes.POINTER(i32)).contents.value
    j = ctypes.cast((u32 * 1)(lr),  ctypes.POINTER(i32)).contents.value
    core.DEBUG('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i = int(float(i) / float(j))
    core.DEBUG('  i=%i (%s)', i, type(i))
    tos.value = i

    core.DEBUG('divl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr))
    self.dump_stack(core)

  def op_modl(self, core):
    core.DEBUG('modl:')

    lr = core.math_registers.pop()
    old_tos = core.math_registers.tos().value
    tos = core.math_registers.tos()

    i = ctypes.cast((u32 * 1)(tos), ctypes.POINTER(i32)).contents.value
    j = ctypes.cast((u32 * 1)(lr),  ctypes.POINTER(i32)).contents.value
    core.DEBUG('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i %= j
    core.DEBUG('  i=%i (%s)', i, type(i))
    tos.value = i

    core.DEBUG('modl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr))
    self.dump_stack(core)

  def op_symmodl(self, core):
    import math

    core.DEBUG('symmodl:')

    lr = core.math_registers.pop()
    old_tos = core.math_registers.tos().value
    tos = core.math_registers.tos()

    i = ctypes.cast((u32 * 1)(tos), ctypes.POINTER(i32)).contents.value
    j = ctypes.cast((u32 * 1)(lr),  ctypes.POINTER(i32)).contents.value
    core.DEBUG('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i = int(math.fmod(i, j))
    core.DEBUG('  i=%i (%s)', i, type(i))
    tos.value = i

    core.DEBUG('modl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr))
    self.dump_stack(core)

VIRTUAL_INTERRUPTS[InterruptList.MATH] = MathInterrupt
