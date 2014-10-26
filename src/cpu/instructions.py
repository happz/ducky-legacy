import collections
import ctypes
import enum
import re

from ctypes import c_ubyte, c_ushort, Structure, Union

from util import *
from mm import UInt16

class Opcodes(enum.IntEnum):
  NOP = 0
  INT = 1
  RETINT = 2
  CLI = 3
  STI = 4
  HLT = 5
  PUSH = 6
  POP = 7
  LOAD = 8
  STORE = 9
  INC = 10
  DEC = 11
  ADD = 12
  SUB = 13
  MUL = 14
  DIV = 15
  JMP = 16
  JE = 17
  JNE = 18
  CALL = 19
  RET = 20
  IN = 21
  OUT = 22
  LOADA = 23
  RST = 24
  CPUID = 25
  IDLE = 26
  JZ = 27
  JNZ = 28
  AND = 29
  OR = 30
  XOR = 31
  NOT = 32
  CMP = 33
  JS  = 34
  JNS = 35
  MOV = 36

class InstructionFlags(enum.IntEnum):
  BYTE = 0

f_ins      = ('ins',    c_ushort)
f_opcode   = ('opcode', c_ubyte, 6)
f_byte     = ('byte',   c_ubyte, 1)
f_flag     = ('flag',   c_ubyte, 1)
f_reg1     = ('reg1',   c_ubyte, 4)
f_reg2     = ('reg2',   c_ubyte, 4)
f_padding4 = ('__padding__', c_ubyte, 4)
f_padding8 = ('__padding__', c_ubyte, 8)

class GenericInstruction(Structure):
  _pack_ = 0
  _fields_ = [f_ins]

class NullaryInstruction(Structure):
  _pack_ = 0
  _fields_ = [f_opcode, f_byte, f_flag, f_padding8]

class UnaryInstruction(Structure):
  _pack_ = 0
  _fields_ = [f_opcode, f_byte, f_flag, f_reg1, f_padding4]

class BinaryInstruction(Structure):
  _pack_ = 0
  _fields_ = [f_opcode, f_byte, f_flag, f_reg1, f_reg2]

class InstructionBinaryFormat(Union):
  _pack_ = 0
  _fields_ = [
    ('generic', GenericInstruction),
    ('nullary', NullaryInstruction),
    ('unary',   UnaryInstruction),
    ('binary',  BinaryInstruction)
  ]

def ins2str(ins):
  orig_ins = ins

  if type(ins) == InstructionBinaryFormat:
    opcode = ins.nullary.opcode
    desc = INSTRUCTIONS[opcode]

    ins = getattr(ins, desc.binary_format)

  opcode = ins.opcode
  desc = INSTRUCTIONS[opcode]

  props = collections.OrderedDict()

  props['ins'] = '%s' % desc.mnemonic
  props['opcode'] = ins.opcode
  props['byte']   = ins.byte

  if desc.binary_format in ('unary', 'binary'):
    props['reg1'] = 'r%i' % ins.reg1

  if desc.binary_format in ('binary',):
    props['reg2'] = 'r%i' % ins.reg2

  return '; '.join(['%s=%s' % (key, value) for key, value in props.items()])

def disassemble_instruction(ins, next_cell):
  if type(ins) == InstructionBinaryFormat:
    opcode = ins.nullary.opcode
    desc = INSTRUCTIONS[opcode]
    ins = getattr(ins, desc.binary_format)
  else:
    desc = INSTRUCTIONS[ins.opcode]

  operands = []

  additional_operands = 0

  for k in range(0, len(desc.args)):
    operand_type = desc.args[k]

    if operand_type == 'r':
      operands.append('r%i' % getattr(ins, 'reg%i' % (k + 1)))

    elif operand_type == 'l':
      operands.append('0x%04X' % next_cell.u16)
      additional_operands += 1

  return (desc.mnemonic.split(' ')[0] + ' ' + ', '.join(operands) + (' b' if ins.byte == 1 else ''), additional_operands)

class InstructionDescriptor(object):
  mnemonic      = None
  pattern       = None
  args          = ''
  binary_format = 'generic'
  opcode        = None
  byte          = False

  def __init__(self):
    super(InstructionDescriptor, self).__init__()

    self.pattern = re.compile(self.pattern)

  def emit_instruction(self, line):
    I = InstructionBinaryFormat()
    I.generic.ins = 0

    record = getattr(I, self.binary_format)
    record.opcode = self.opcode

    refers_to = None

    match = self.pattern.match(line).groups()

    debug('line: "%s"' % line)

    for i in range(0, len(self.args)):
      # register
      if self.args[i] == 'r':
        setattr(record, 'reg%i' % (i + 1), int(match[i]))

      # label
      if self.args[i] == 'l':
        debug('label operand: %s' % str(match))
        if match[i]:
          refers_to = UInt16(int(match[i], base = 16))
        elif match[i + 4]:
          refers_to = match[i + 4]
        elif match[i + 3]:
          refers_to = match[i + 3]
        else:
          refers_to = UInt16()
          refers_to.u16 = int(match[i + 2])

    if self.byte and line.endswith(' b'):
      record.byte = 1

    return [I] if not refers_to else [I, refers_to]

p_r  = r'r(\d{1,2})'
p_l  = r'(?:(0x([0-9a-fA-F]+))|(\d+)|(&[a-zA-Z_][a-zA-Z0-9_]*)|([a-zA-Z_][a-zA-Z0-9_-]*))'
p_rr = r'' + p_r + ', ' + p_r
p_rl = r'' + p_r + ', ' + p_l

class Ins_NOP(InstructionDescriptor):
  mnemonic = 'nop'
  pattern = r'nop'
  binary_format = 'nullary'
  opcode = Opcodes.NOP

class Ins_INT(InstructionDescriptor):
  mnemonic = 'int <reg>'
  pattern = r'int ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.INT

class Ins_RETINT(InstructionDescriptor):
  mnemonic = 'retint'
  pattern = r'retint'
  binary_format = 'nullary'
  opcode = Opcodes.RETINT

class Ins_CLI(InstructionDescriptor):
  mnemonic = 'cli'
  pattern = r'cli'
  binary_format = 'nullary'
  opcode = Opcodes.CLI

class Ins_STI(InstructionDescriptor):
  mnemonic = 'sti'
  pattern = r'sti'
  binary_format = 'nullary'
  opcode = Opcodes.STI

class Ins_HLT(InstructionDescriptor):
  mnemonic = 'hlt <reg>'
  pattern = r'hlt ' + p_r
  binary_format = 'unary'
  args = 'r'
  opcode = Opcodes.HLT

class Ins_PUSH(InstructionDescriptor):
  mnemonic = 'push <reg>'
  pattern = r'push ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.PUSH

class Ins_POP(InstructionDescriptor):
  mnemonic = 'pop <reg>'
  pattern = r'pop ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.POP

class Ins_LOAD(InstructionDescriptor):
  mnemonic = 'load <reg>, <reg>'
  pattern = r'load ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.LOAD
  byte = True

class Ins_STORE(InstructionDescriptor):
  mnemonic = 'store <reg>, <reg>'
  pattern = r'store ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.STORE
  byte = True

class Ins_INC(InstructionDescriptor):
  mnemonic = 'inc <reg>'
  pattern = r'inc ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.INC

class Ins_DEC(InstructionDescriptor):
  mnemonic = 'dec <reg>'
  pattern = r'dec ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.DEC

class Ins_ADD(InstructionDescriptor):
  mnemonic = 'add <reg>, <reg>'
  pattern = r'add ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.ADD

class Ins_SUB(InstructionDescriptor):
  mnemonic = 'sub <reg>, <reg>'
  pattern = r'sub ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.SUB

class Ins_MUL(InstructionDescriptor):
  mnemonic = 'mul <reg>, <reg>'
  pattern = r'mul ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.MUL

class Ins_DIV(InstructionDescriptor):
  mnemonic = 'div <reg>, <reg>'
  pattern = r'div ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.DIV

class Ins_JMP(InstructionDescriptor):
  mnemonic = 'jmp [label]'
  pattern = r'jmp ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JMP

class Ins_JE(InstructionDescriptor):
  mnemonic = 'je [label]'
  pattern = r'je ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JE

class Ins_JNE(InstructionDescriptor):
  mnemonic = 'jne [label]'
  pattern = r'jne ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JNE

class Ins_CALL(InstructionDescriptor):
  mnemonic = 'call [label]'
  pattern = r'call ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.CALL

class Ins_RET(InstructionDescriptor):
  mnemonic = 'ret'
  pattern = r'ret'
  binary_format = 'nullary'
  opcode = Opcodes.RET

class Ins_IN(InstructionDescriptor):
  mnemonic = 'in <reg>, <reg>'
  pattern = r'in ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.IN
  byte = True

class Ins_OUT(InstructionDescriptor):
  mnemonic = 'out <reg>, <reg>'
  pattern = r'out ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.OUT
  byte = True

class Ins_LOADA(InstructionDescriptor):
  mnemonic = 'loada <reg>, [label]'
  pattern = r'loada ' + p_rl
  args = 'rl'
  binary_format = 'binary'
  opcode = Opcodes.LOADA

class Ins_RST(InstructionDescriptor):
  mnemonic = 'rst'
  pattern = r'rst'
  binary_format = 'nullary'
  opcode = Opcodes.RST

class Ins_CPUID(InstructionDescriptor):
  mnemonic = 'cpuid <reg>'
  pattern = r'cpuid ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.CPUID

class Ins_IDLE(InstructionDescriptor):
  mnemonic = 'idle'
  pattern = r'idle'
  binary_format = 'nullary'
  opcode = Opcodes.IDLE

class Ins_JZ(InstructionDescriptor):
  mnemonic = 'jz [label]'
  pattern = r'jz ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JZ

class Ins_JNZ(InstructionDescriptor):
  mnemonic = 'jnz [label]'
  pattern = r'jnz ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JNZ

class Ins_AND(InstructionDescriptor):
  mnemonic = 'and <reg>, <reg>'
  pattern = r'and ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.AND

class Ins_OR(InstructionDescriptor):
  mnemonic = 'or <reg>, <reg>'
  pattern = r'or ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.OR

class Ins_XOR(InstructionDescriptor):
  mnemonic = 'xor <reg>, <reg>'
  pattern = r'xor ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.XOR

class Ins_NOT(InstructionDescriptor):
  mnemonic = 'not <reg>'
  pattern = r'not ' + p_r
  args = 'r'
  binary_format = 'unary'
  opcode = Opcodes.NOT

class Ins_CMP(InstructionDescriptor):
  mnemonic = 'cmp <reg>, <reg>'
  pattern = r'cmp ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.CMP

class Ins_JS(InstructionDescriptor):
  mnemonic = 'js [label]'
  pattern = r'js ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JS

class Ins_JNS(InstructionDescriptor):
  mnemonic = 'jns [label]'
  pattern = r'jns ' + p_l
  args = 'l'
  binary_format = 'nullary'
  opcode = Opcodes.JNS

class Ins_MOV(InstructionDescriptor):
  mnemonic = 'mov <reg>, <reg>'
  pattern = r'mov ' + p_rr
  args = 'rr'
  binary_format = 'binary'
  opcode = Opcodes.MOV

INSTRUCTIONS = [
  Ins_NOP(),
  Ins_INT(),
  Ins_RETINT(),
  Ins_CLI(),
  Ins_STI(),
  Ins_HLT(),
  Ins_PUSH(),
  Ins_POP(),
  Ins_LOAD(),
  Ins_STORE(),
  Ins_INC(),
  Ins_DEC(),
  Ins_ADD(),
  Ins_SUB(),
  Ins_MUL(),
  Ins_DIV(),
  Ins_JMP(),
  Ins_JE(),
  Ins_JNE(),
  Ins_CALL(),
  Ins_RET(),
  Ins_IN(),
  Ins_OUT(),
  Ins_LOADA(),
  Ins_RST(),
  Ins_CPUID(),
  Ins_IDLE(),
  Ins_JZ(),
  Ins_JNZ(),
  Ins_AND(),
  Ins_OR(),
  Ins_XOR(),
  Ins_NOT(),
  Ins_CMP(),
  Ins_JS(),
  Ins_JNS(),
  Ins_MOV()
]

PATTERNS = [id.pattern for id in INSTRUCTIONS]

