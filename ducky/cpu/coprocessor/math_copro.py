"""
Stack-based coprocessor, providing several arithmetic operations with "long"
numbers.

Coprocessor's instructions operates above stack of (by default) 8 slots.
Operations to move values between math stack and regular registers are also
available.

In the following documentation several different data types are used:

 - ``int`` - standard `word`, 32-bit wide integer
 - ``long`` - long integer, 64-bit wide

Unless said otherwise, instruction takes its arguments from the stack, removing
the values in the process, and pushes the result - if any - back on the stack.
"""

import enum

from ...interfaces import ISnapshotable
from . import Coprocessor
from .. import CPUException
from ..instructions import InstructionSet, SIS, INSTRUCTION_SETS, Descriptor_RI
from ...mm import u32_t, i64_t, u64_t, UINT64_FMT
from ...snapshot import SnapshotNode

#: Number of available spots on the math stack.
STACK_DEPTH = 8

class MathCoprocessorState(SnapshotNode):
  """
  Snapshot node holding the state of math coprocessor.
  """

  def __init__(self):
    super(MathCoprocessorState, self).__init__('stack')

class EmptyMathStackError(CPUException):
  """
  Raised when operation expects at least one value on math stack but stack
  is empty.
  """

  def __init__(self, *args, **kwargs):
    super(EmptyMathStackError, self).__init__('Math stack is empty', *args, **kwargs)

class FullMathStackError(CPUException):
  """
  Raised when operation tries to put value on math stack but there is no empty
  spot available.
  """

  def __init__(self, *args, **kwargs):
    super(FullMathStackError, self).__init__('Math stack is full', *args, **kwargs)

class RegisterSet(ISnapshotable):
  """
  Math stack wrapping class. Provides basic push/pop access, and direct access
  to a top of the stack.

  :param ducky.cpu.CPUCore core: CPU core registers belong to.
  """

  def __init__(self, core):
    super(RegisterSet, self).__init__()

    self.core = core
    self.stack = []

    self.DEBUG = core.DEBUG

  def save_state(self, parent):
    self.DEBUG('RegisterSet.save_state')

    state = parent.add_child('math_coprocessor', MathCoprocessorState())

    state.stack = []
    for lr in self.stack:
      state.stack.append(int(lr.value))

  def load_state(self, state):
    self.DEBUG('RegisterSet.load_state')

    for lr in state.depth:
      self.stack.append(u64_t(lr))

  def push(self, v):
    """
    Push new value on top of the stack.

    :raises ducky.cpu.coprocessor.math_copro.FullMathStackError: if there is no space available on the stack.
    """

    self.DEBUG('%s.push: v=%s', self.__class__.__name__, UINT64_FMT(v))

    if len(self.stack) == STACK_DEPTH:
      raise FullMathStackError()

    self.stack.append(v)

  def pop(self):
    """
    Pop the top value from stack and return it.

    :raises ducky.cpu.coprocessor.math_copro.EmptyMathStackError: if there are no values on the stack.
    """

    self.DEBUG('%s.pop', self.__class__.__name__)

    if not self.stack:
      raise EmptyMathStackError()

    return self.stack.pop()

  def tos(self):
    """
    Return the top of the stack, without removing it from a stack.

    :raises ducky.cpu.coprocessor.math_copro.EmptyMathStackError: if there are no values on the stack.
    """

    self.DEBUG('%s.tos', self.__class__.__name__)

    if not self.stack:
      raise EmptyMathStackError()

    return self.stack[-1]

  def tos1(self):
    """
    Return the item below the top of the stack, without removing it from a stack.

    :raises ducky.cpu.coprocessor.math_copro.EmptyMathStackError: if there are no values on the stack.
    """

    self.DEBUG('%s.tos', self.__class__.__name__)

    if len(self.stack) < 2:
      raise EmptyMathStackError()

    return self.stack[-2]

class MathCoprocessor(ISnapshotable, Coprocessor):
  """
  Coprocessor itself, includes its register set ("math stack").

  :param ducky.cpu.CPUCore core: CPU core coprocessor belongs to.
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
      D('#%02i: %s', index, UINT64_FMT(lr.value))

    D('---')

  def sign_extend_with_push(self, i32):
    v = u64_t(i32)

    if i32 & 0x80000000:
      v.value |= 0xFFFFFFFF00000000

    self.registers.push(v)

  def extend_with_push(self, u32):
    self.registers.push(u64_t(u32))

#
# Instruction set
#
class MathCoprocessorOpcodes(enum.IntEnum):
  """
  Math coprocessor's instruction opcodes.
  """

  POPW    = 0
  POPUW   = 1
  PUSHW   = 2

  POP     = 3
  PUSH    = 4

  MULL    = 10
  DIVL    = 11
  MODL    = 12
  SYMDIVL = 13
  SYMMODL = 14

  DUP     = 20
  DUP2    = 21
  SWAP    = 22

  INCL    =  30
  DECL    =  31

  SIS     = 63

class MathCoprocessorInstructionSet(InstructionSet):
  """
  Math coprocessor's instruction set.
  """

  instruction_set_id = 1

  opcodes = MathCoprocessorOpcodes

class Descriptor_MATH(Descriptor_RI):
  operands = ''

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    pass

  @staticmethod
  def disassemble_operands(logger, inst):
    pass

class PUSHW(Descriptor_MATH):
  """
  Downsize the TOS to ``int``, and push the result on the regular stack.
  """

  mnemonic = 'pushw'
  opcode = MathCoprocessorOpcodes.PUSHW

  @staticmethod
  def execute(core, inst):
    core.raw_push(u32_t(core.math_coprocessor.registers.pop().value & 0xFFFFFFFF).value)

class POPW(Descriptor_MATH):
  """
  Pop the ``int``from regular stack, extend it to ``long``, and push the value on the stack.
  """

  mnemonic = 'popw'
  opcode = MathCoprocessorOpcodes.POPW

  @staticmethod
  def execute(core, inst):
    core.math_coprocessor.sign_extend_with_push(core.raw_pop())

class POPUW(Descriptor_MATH):
  """
  Pop the ``int``from regular stack, extend it to ``long``, and push the value on the stack.
  """

  mnemonic = 'popuw'
  opcode = MathCoprocessorOpcodes.POPUW

  @staticmethod
  def execute(core, inst):
    core.math_coprocessor.extend_with_push(core.raw_pop())

class PUSH(Descriptor_MATH):
  """
  Push the TOS on the regular stack.
  """

  mnemonic = 'push'
  opcode = MathCoprocessorOpcodes.PUSH

  @staticmethod
  def execute(core, inst):
    v = core.math_coprocessor.registers.pop()

    core.raw_push(v.value & 0xFFFFFFFF)
    core.raw_push(v.value >> 32)

class POP(Descriptor_MATH):
  """
  Pop the ``long`` from regular stack, and push it on the stack.
  """

  mnemonic = 'pop'
  opcode = MathCoprocessorOpcodes.POP

  @staticmethod
  def execute(core, inst):
    hi = core.raw_pop()
    lo = core.raw_pop()

    core.math_coprocessor.registers.push(u64_t((hi << 32) | lo))

class INCL(Descriptor_MATH):
  """
  Increment top of the stack by one.
  """

  mnemonic = 'incl'
  opcode = MathCoprocessorOpcodes.INCL

  @staticmethod
  def execute(core, inst):
    core.math_coprocessor.registers.tos().value += 1

class DECL(Descriptor_MATH):
  """
  Decrement top of the stack by one.
  """

  mnemonic = 'decl'
  opcode = MathCoprocessorOpcodes.DECL

  @staticmethod
  def execute(core, inst):
    core.math_coprocessor.registers.tos().value -= 1

class MULL(Descriptor_MATH):
  """
  Multiply two top-most numbers on the stack.
  """

  mnemonic = 'mull'
  opcode = MathCoprocessorOpcodes.MULL

  @staticmethod
  def execute(core, inst):
    RS = core.math_coprocessor.registers

    a = RS.pop()
    b = RS.pop()

    RS.push(u64_t(a.value * b.value))

class DIVL(Descriptor_MATH):
  """
  Divide the value below the top of the math stack by the topmost value.
  """

  mnemonic = 'divl'
  opcode = MathCoprocessorOpcodes.DIVL

  @staticmethod
  def execute(core, inst):
    RS = core.math_coprocessor.registers

    divider = i64_t(RS.pop().value)
    tos = i64_t(RS.pop().value)

    RS.push(u64_t(tos.value // divider.value))

class MODL(Descriptor_MATH):
  mnemonic = 'modl'
  opcode = MathCoprocessorOpcodes.MODL

  @staticmethod
  def execute(core, inst):
    RS = core.math_coprocessor.registers

    divider = i64_t(RS.pop().value)
    tos = i64_t(RS.pop().value)

    RS.push(u64_t(tos.value % divider.value))

class DUP(Descriptor_MATH):
  mnemonic = 'dup'
  opcode = MathCoprocessorOpcodes.DUP

  @staticmethod
  def execute(core, inst):
    M = core.math_coprocessor

    M.registers.push(u64_t(M.registers.tos().value))

class DUP2(Descriptor_MATH):
  mnemonic = 'dup2'
  opcode = MathCoprocessorOpcodes.DUP2

  @staticmethod
  def execute(core, inst):
    M = core.math_coprocessor

    a = M.registers.pop()
    b = M.registers.pop()
    M.registers.push(b)
    M.registers.push(a)
    M.registers.push(u64_t(b.value))
    M.registers.push(u64_t(a.value))

class SWAP(Descriptor_MATH):
  mnemonic = 'swap'
  opcode = MathCoprocessorOpcodes.SWAP

  @staticmethod
  def execute(core, inst):
    M = core.math_coprocessor

    a = M.registers.pop()
    b = M.registers.pop()
    M.registers.push(a)
    M.registers.push(b)

class SYMDIVL(Descriptor_MATH):
  """
  The same operation like ``DIVL`` but provides symmetric results.
  """

  mnemonic = 'symdivl'
  opcode = MathCoprocessorOpcodes.SYMDIVL

  @staticmethod
  def execute(core, inst):
    RS = core.math_coprocessor.registers

    divider = i64_t(RS.pop().value)
    tos = i64_t(RS.pop().value)

    RS.push(u64_t(int(tos.value // divider.value)))

class SYMMODL(Descriptor_MATH):
  mnemonic = 'symmodl'
  opcode = MathCoprocessorOpcodes.SYMMODL

  @staticmethod
  def execute(core, inst):
    import math

    RS = core.math_coprocessor.registers

    divider = i64_t(RS.pop().value)
    tos = i64_t(RS.pop().value)

    RS.push(u64_t(int(math.fmod(tos.value, divider.value))))

INCL(MathCoprocessorInstructionSet)
DECL(MathCoprocessorInstructionSet)
MULL(MathCoprocessorInstructionSet)
DIVL(MathCoprocessorInstructionSet)
MODL(MathCoprocessorInstructionSet)
SYMDIVL(MathCoprocessorInstructionSet)
SYMMODL(MathCoprocessorInstructionSet)
DUP(MathCoprocessorInstructionSet)
DUP2(MathCoprocessorInstructionSet)
SWAP(MathCoprocessorInstructionSet)
PUSHW(MathCoprocessorInstructionSet)
POPW(MathCoprocessorInstructionSet)
POPUW(MathCoprocessorInstructionSet)
PUSH(MathCoprocessorInstructionSet)
POP(MathCoprocessorInstructionSet)
SIS(MathCoprocessorInstructionSet)

MathCoprocessorInstructionSet.init()

INSTRUCTION_SETS[MathCoprocessorInstructionSet.instruction_set_id] = MathCoprocessorInstructionSet
