"""
Stack-based coprocessor, providing several arithmetic operations with "long",
32 bits wide integers.

Coprocessor's instructions operates above stack of 8 long ints. Operations to
move values between math stack and regular registers are also available.

Operations usually consume their operands from the stack, and push the result
back.
"""

import enum

from cpu.coprocessor import Coprocessor
from cpu.registers import Registers
from mm import u32, i32, UINT32_FMT, UINT16_FMT
from irq import InterruptList
from irq.virtual import VIRTUAL_INTERRUPTS, VirtualInterrupt
from snapshot import SnapshotNode, ISnapshotable

STACK_DEPTH = 8

class MathCoprocessorState(SnapshotNode):
  def __init__(self):
    super(MathCoprocessorState, self).__init__('stack')

class MathOperationList(enum.IntEnum):
  """
  List of available arithmetic operations.
  """

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

class RegisterSet(ISnapshotable, object):
  """
  Math stack wrapping class. Provides basic push/pop access, and direct access
  to a top of the stack.
  """

  def __init__(self, core):
    super(RegisterSet, self).__init__()

    self.core = core
    self.stack = []

  def save_state(self, parent):
    self.core.DEBUG('RegisterSet.save_state')

    state = parent.add_child('math_coprocessor', MathCoprocessorState())

    state.stack = []
    for lr in self.stack:
      state.stack.append(int(lr.value))

  def load_state(self, state):
    self.core.DEBUG('RegisterSet.load_state')

    for lr in state.depth:
      self.stack.append(u32(lr))

  def push(self, v):
    """
    Push new value on top of the stack.

    :raises FullMathStackError: if there is no space available on the stack.
    """

    if len(self.stack) == STACK_DEPTH:
      raise FullMathStackError()

    self.stack.append(v)

  def pop(self):
    """
    Pop the top value from stack and return it.

    :raises EmptyMathStackError: if there are no values on the stack.
    """

    if not self.stack:
      raise EmptyMathStackError()

    return self.stack.pop()

  def tos(self):
    """
    Return the top of the stack, without removing it from a stack.

    :raises EmptyMathStackError: if there are no values on the stack.
    """

    if not self.stack:
      raise EmptyMathStackError()

    return self.stack[-1]

class MathCoprocessor(ISnapshotable, Coprocessor):
  """
  Coprocessor itself, includes its register set ("math stack").
  """

  def __init__(self, core, *args, **kwargs):
    super(MathCoprocessor, self).__init__(core, *args, **kwargs)

    self.registers = RegisterSet(core)

  def save_state(self, parent):
    self.registers.save_state(parent)

  def load_state(self, state):
    self.registers.load_state(state)

  def dump_stack(self):
    """
    Log content of the stack using parent's ``DEBUG`` method.
    """

    D = self.core.DEBUG

    D('Math stack:')

    for index, lr in enumerate(self.registers.stack):
      D('#%02i: %s', index, UINT32_FMT(lr.value))

    D('---')

  def op_itol(self):
    """
    Extend 16bit int to 32bit long int. Int is read from `r1`. Signed extension
    is used.
    """

    D = self.core.DEBUG

    r = self.core.REG(Registers.R01)
    lr = u32(r.value)

    if r.value & 0x8000 != 0:
      lr.value |= 0xFFFF0000

    self.registers.push(lr)

    D('itol: i=%s', UINT16_FMT(r.value))
    self.dump_stack()

  def op_utol(self):
    """
    Extend 16bit int to 32bit long int. Int is read from `r1`.
    """

    D = self.core.DEBUG

    r = self.core.REG(Registers.R01)
    lr = u32(r.value)

    self.registers.push(lr)

    D('utol: i=%s', UINT16_FMT(r.value))
    self.dump_stack()

  def op_iitol(self):
    """
    Merge two 16bit ints to 32bit long int. Ints are read from `r1` (lower
    bytes) and `r2` (higher bytes).
    """

    D = self.core.DEBUG

    r1 = self.core.REG(Registers.R01)
    r2 = self.core.REG(Registers.R02)
    lr = u32(r1.value | (r2.value << 16))

    self.registers.push(lr)

    D('iitol: lb=%s, hb=%s', UINT16_FMT(r1.value), UINT16_FMT(r2.value))
    self.dump_stack()

  def op_ltoi(self):
    """
    Truncate 32bit long int to 16bit int. New int is stored in `r1` register.
    """

    D = self.core.DEBUG

    lr = self.registers.pop()

    self.core.check_protected_reg(Registers.R01)
    self.core.REG(Registers.R01).value = lr.value & 0xFFFF

    D('ltoi: i=%s', UINT16_FMT(self.core.REG(Registers.R01).value))
    self.dump_stack()

  def op_ltoii(self):
    """
    Split 32bit long into to two 16bit ints. New ints are stored in `r1` (lower
    bytes) and `r2` (higher bytes).
    """

    D = self.core.DEBUG

    r1 = self.core.REG(Registers.R01)
    r2 = self.core.REG(Registers.R02)
    lr = self.registers.pop()

    self.core.check_protected_reg(Registers.R01, Registers.R02)
    r1.value =  lr.value & 0x0000FFFF
    r2.value = (lr.value & 0xFFFF0000) >> 16

    D('ltoii: lb=%s, hb=%s', UINT16_FMT(r1.value), UINT16_FMT(r2.value))
    self.dump_stack()

  def op_dupl(self):
    """
    Duplicate top of the math stack.
    """

    D = self.core.DEBUG

    lr = self.registers.tos()

    self.registers.push(u32(lr.value))

    D('dupl:')
    self.dump_stack()

  def op_incl(self):
    """
    Increment top of the stack by one.
    """

    self.registers.tos().value += 1

  def op_decl(self):
    """
    Decrement top of the stack by one.
    """

    self.registers.tos().value -= 1

  def op_addl(self):
    """
    Add the topmost value to the value below.
    """

    lr = self.registers.pop()

    self.registers.tos().value += lr.value

  def op_subl(self):
    """
    Subtract the top value from the value bellow.
    """

    lr = self.registers.pop()

    self.registers.tos().value -= lr.value

  def op_mull(self):
    """
    Multiply two topmost values.
    """

    D = self.core.DEBUG

    lr = self.registers.pop()
    old_tos = self.registers.tos().value

    self.registers.tos().value *= lr.value

    D('mull: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr.value))
    self.dump_stack()

  def op_divl(self):
    """
    Divide the value below the top of the math stack by the topmost value.
    """

    D = self.core.DEBUG

    D('divl:')

    lr = self.registers.pop()
    old_tos = self.registers.tos().value
    tos = self.registers.tos()

    i = i32(tos.value).value
    j = i32(lr.value).value
    D('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i /= j
    D('  i=%i (%s)', i, type(i))
    tos.value = i

    D('divl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr.value))
    self.dump_stack()

  def op_symdivl(self):
    """
    The same operation like ``DIVL`` but provides symmetric results.
    """

    D = self.core.DEBUG

    D('symdivl:')

    lr = self.registers.pop()
    old_tos = self.registers.tos().value
    tos = self.registers.tos()

    i = i32(tos.value).value
    j = i32(lr.value).value
    D('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i = int(float(i) / float(j))
    D('  i=%i (%s)', i, type(i))
    tos.value = i

    D('divl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr.value))
    self.dump_stack()

  def op_modl(self):
    """
    Computes remainder after division. The value below the top of the math
    stack is divided by the topmost value, and remainder is pushed back to
    stack.
    """

    D = self.core.DEBUG

    D('modl:')

    lr = self.registers.pop()
    old_tos = self.registers.tos().value
    tos = self.registers.tos()

    i = i32(tos.value).value
    j = i32(lr.value).value
    D('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i %= j
    D('  i=%i (%s)', i, type(i))
    tos.value = i

    D('modl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr.value))
    self.dump_stack()

  def op_symmodl(self):
    """
    The same operations as ``MODL`` but provides symmetric results.
    """

    import math

    D = self.core.DEBUG

    D('symmodl:')

    lr = self.registers.pop()
    old_tos = self.registers.tos().value
    tos = self.registers.tos()

    i = i32(tos.value).value
    j = i32(lr.value).value
    D('  i=%i, j=%i (%s, %s)', i, j, type(i), type(j))
    i = int(math.fmod(i, j))
    D('  i=%i (%s)', i, type(i))
    tos.value = i

    D('modl: %s %s', UINT32_FMT(old_tos), UINT32_FMT(lr.value))
    self.dump_stack()

class MathInterrupt(VirtualInterrupt):
  """
  Virtual interrupt handler of math coprocessor.
  """

  def run(self, core):
    """
    Called when coprocessor's interrupt is triggered. Dispatches call to a proper
    method to handle requested operation.

    Id of requested operation is expected in `r0`.
    """

    core.DEBUG('MathInterrupt: triggered')

    op = core.REG(Registers.R00).value
    core.REG(Registers.R00).value = 0

    if op == MathOperationList.ITOL:
      core.math_coprocessor.op_itol()

    elif op == MathOperationList.UTOL:
      core.math_coprocessor.op_utol()

    elif op == MathOperationList.IITOL:
      core.math_coprocessor.op_iitol()

    elif op == MathOperationList.LTOI:
      core.math_coprocessor.op_ltoi()

    elif op == MathOperationList.LTOII:
      core.math_coprocessor.op_ltoii()

    elif op == MathOperationList.DUPL:
      core.math_coprocessor.op_dupl()

    elif op == MathOperationList.INCL:
      core.math_coprocessor.op_incl()

    elif op == MathOperationList.DECL:
      core.math_coprocessor.op_decl()

    elif op == MathOperationList.ADDL:
      core.math_coprocessor.op_addl()

    elif op == MathOperationList.SUBL:
      core.math_coprocessor.op_subl()

    elif op == MathOperationList.MULL:
      core.math_coprocessor.op_mull()

    elif op == MathOperationList.DIVL:
      core.math_coprocessor.op_divl()

    elif op == MathOperationList.MODL:
      core.math_coprocessor.op_modl()

    elif op == MathOperationList.SYMDIVL:
      core.math_coprocessor.op_symdivl()

    elif op == MathOperationList.SYMMODL:
      core.math_coprocessor.op_symmodl()

    else:
      core.WARN('Unknown math operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

VIRTUAL_INTERRUPTS[InterruptList.MATH] = MathInterrupt
