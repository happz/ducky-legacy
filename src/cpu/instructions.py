import collections
import ctypes
import enum
import re
import types

from ctypes import LittleEndianStructure, Union, c_uint, c_int

from util import debug
from mm import UInt32, UInt16, UINT16_FMT, ADDR_FMT, OFFSET_FMT
from cpu.registers import Registers, REGISTER_NAMES
from cpu.errors import CompilationError, InvalidOpcode

class Opcodes(enum.IntEnum):
  NOP    =  0

  LW     =  1
  LB     =  2
  #      =  3
  LI     =  4
  STW    =  5
  STB    =  6
  #      =  7
  MOV    =  8
  SWP    =  9
  CAS    = 10

  INT    = 11
  RETINT = 12

  CALL   = 13
  RET    = 14

  CLI    = 15
  STI    = 16
  RST    = 17
  HLT    = 18
  IDLE   = 19

  PUSH   = 20
  POP    = 21

  INC    = 22
  DEC    = 23
  ADD    = 24
  SUB    = 25
  MUL    = 26

  AND    = 27
  OR     = 28
  XOR    = 29
  NOT    = 30
  SHIFTL = 31
  SHIFTR = 32

  OUT    = 33
  IN     = 34
  OUTB   = 35
  INB    = 36

  CMP    = 37
  J      = 38
  BE     = 39
  BNE    = 40
  BZ     = 41
  BNZ    = 42
  BS     = 43
  BNS    = 44
  BG     = 45
  BGE    = 46
  BL     = 47
  BLE    = 48

  DIV    = 49
  MOD    = 50

  CMPU   = 51

class GenericInstBinaryFormat_Overall(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u32', c_uint)
  ]

class GenericInstBinaryFormat_Opcode(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('opcode', c_uint, 6),
    ('__padding__', c_uint, 26)
  ]

def decode_instruction(inst):
  if type(inst) == UInt32:
    master = InstBinaryFormat_Master()
    master.overall.u32 = inst.u32
    inst = master

  if type(inst) == InstBinaryFormat_Master:
    if inst.opcode.opcode not in OPCODE_TO_DESC_MAP:
      raise InvalidOpcode(inst.opcode.opcode)

    return getattr(inst, OPCODE_TO_DESC_MAP[inst.opcode.opcode].binary_format_name)

  return inst

def convert_to_master(inst):
  if isinstance(inst, InstBinaryFormat_Master):
    return inst

  master = InstBinaryFormat_Master()
  setattr(master, inst.__class__.__name__, inst)
  return master

def disassemble_instruction(inst):
  inst = decode_instruction(inst)
  desc = OPCODE_TO_DESC_MAP[inst.opcode]

  operands = desc.disassemble_operands(inst)

  return (desc.mnemonic + ' ' + ', '.join(operands)) if len(operands) else desc.mnemonic


PO_REGISTER  = r'(?P<register_n{operand_index}>(?:r\d\d?)|(?:sp)|(?:fp)|(?:ds))'
PO_AREGISTER = r'(?P<address_register>(?:r(\d\d?)|(sp)|(fp)))(?:\[(?P<shift>-)?(?P<offset>(?:0x[0-9a-fA-F]+|\d+))\])?'
PO_IMMEDIATE = r'(?:(?P<immediate_hex>-?0x[0-9a-fA-F]+)|(?P<immediate_dec>-?\d+)|(?P<immediate_address>&[a-zA-Z_\.][a-zA-Z0-9_]*))'


def BF_FLG(n):
  return '%s:1' % n

def BF_REG(*args):
  args = args or ['reg']
  return '%s:4' % args[0]

def BF_IMM(*args):
  args = args or ['immediate']
  return '%s:17:int' % args[0]


class InstDescriptor(object):
  mnemonic      = None
  opcode        = None
  operands      = None
  binary_format = None

  pattern       = None
  binary_format_name = None

  relative_address = False

  def create_binary_format_class(self):
    fields = []

    fields_desc = self.binary_format if self.binary_format else []

    if not len(fields_desc) or not fields_desc[0].startswith('opcode'):
      fields_desc.insert(0, 'opcode:6')

    for field in fields_desc:
      field = field.split(':')
      data_type = c_int if len(field) == 3 else c_uint
      fields.append((field[0], data_type, int(field[1])))

    self.binary_format_name = 'InstBinaryFormat_%s' % self.mnemonic
    self.binary_format = type(self.binary_format_name, (ctypes.LittleEndianStructure,), {'_pack_': 0, '_fields_': fields})

    self.binary_format.__repr__ = lambda inst: '<' + disassemble_instruction(inst) + '>'

  def __init__(self):
    super(InstDescriptor, self).__init__()

    pattern = self.mnemonic

    if self.operands:
      operand_patterns = []

      self.operands = [ot.strip() for ot in self.operands.split(',')]

      for operand_index, operand_types in zip(range(0, len(self.operands)), self.operands):
        operand_pattern = []

        for operand_type in operand_types:
          if operand_type == 'r':
            operand_pattern.append(PO_REGISTER.format(operand_index = operand_index))

          elif operand_type == 'a':
            operand_pattern.append(PO_AREGISTER)

          elif operand_type == 'i':
            operand_pattern.append(PO_IMMEDIATE)

          else:
            raise Exception('Unhandled operand type: %s' % operand_type)

        operand_patterns.append('(?:' + '|'.join(operand_pattern) + ')')

      pattern += ' ' + ', '.join(operand_patterns)

    self.pattern = re.compile(pattern)

    self.create_binary_format_class()

  def assemble_operands(self, inst, operands):
    pass

  def fix_refers_to(self, inst, refers_to):
    pass

  def disassemble_operands(self, inst):
    # pylint: disable-msg=W0613
    return []

  def emit_instruction(self, line):
    debug('emit_instruction: %s' % line)

    master = InstBinaryFormat_Master()
    master.overall.u16 = 0

    debug('emit_instruction: binary format is %s' % self.binary_format_name)
    debug('emit_instruction: desc is %s' % self)

    real = getattr(master, self.binary_format_name)
    real.opcode = self.opcode

    raw_match = self.pattern.match(line)
    matches = raw_match.groupdict()
    debug('emit_instruction: matches=%s' % matches)

    operands = []

    if self.operands and len(self.operands):
      for operand_index in range(0, len(self.operands)):
        reg_group_name = 'register_n%i' % operand_index

        if reg_group_name in matches and matches[reg_group_name]:
          reg = matches[reg_group_name]

          if reg == 'sp':
            operands.append(Registers.SP)

          elif reg == 'ds':
            operands.append(Registers.DS)

          elif reg == 'fp':
            operands.append(Registers.FP)

          else:
            operands.append(Registers(int(reg[1:])))

        elif 'address_register' in matches and matches['address_register']:
          reg = matches['address_register']

          if reg == 'fp':
            operands.append(Registers.FP)

          elif reg == 'sp':
            operands.append(Registers.SP)

          else:
            operands.append(Registers(int(reg[1:])))

          if 'offset' in matches and matches['offset']:
            k = -1 if 'shift' in matches and matches['shift'] and matches['shift'].strip() == '-' else 1

            if matches['offset'].startswith('0x'):
              operands.append(int(matches['offset'], base = 16) * k)

            else:
              operands.append(int(matches['offset']) * k)

        elif 'immediate_hex' in matches and matches['immediate_hex']:
          operands.append(int(matches['immediate_hex'], base = 16))

        elif 'immediate_dec' in matches and matches['immediate_dec']:
          operands.append(int(matches['immediate_dec']))

        elif 'immediate_address' in matches and matches['immediate_address']:
          operands.append(matches['immediate_address'])

        else:
          raise Exception('Unhandled operand: %s' % matches)

    else:
      pass

    self.assemble_operands(real, operands)

    for flag in [f for f in dir(self) if f.startswith('flag_')]:
      setattr(real, flag.split('_')[1], getattr(self, flag))

    return real


class InstDescriptor_Generic(InstDescriptor):
  pass

class InstDescriptor_Generic_Unary_R(InstDescriptor):
  operands = 'r'
  binary_format = [BF_REG()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[0]

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg]]

class InstDescriptor_Generic_Unary_RI(InstDescriptor):
  operands      = 'ri'
  binary_format = [BF_FLG('is_reg'), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    v = operands[0]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif type(v) == types.IntType:
      inst.is_reg = 0
      inst.immediate = v

    elif type(v) == types.StringType:
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, OFFSET_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_I(InstDescriptor):
  operands = 'r,i'
  binary_format = [BF_REG(), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[0]

    v = operands[1]

    if type(v) == types.IntType:
      inst.immediate = v

    else:
      inst.refers_to = v

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg], inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [REGISTER_NAMES[inst.reg], OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_RI(InstDescriptor):
  operands = 'r,ri'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[0]

    v = operands[1]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif type(v) == types.IntType:
      inst.is_reg = 0
      inst.immediate = v

    elif type(v) == types.StringType:
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.reg], REGISTER_NAMES[inst.ireg]]

    return [REGISTER_NAMES[inst.reg], inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_RI_R(InstDescriptor):
  operands = 'ri,r'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[1]

    v = operands[0]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif type(v) == types.IntType:
      inst.is_reg = 0
      inst.immediate = v

    elif type(v) == types.StringType:
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg], REGISTER_NAMES[inst.reg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate), REGISTER_NAMES[inst.reg]]

class InstDescriptor_Generic_Binary_R_A(InstDescriptor):
  operands = 'r,a'
  binary_format = [BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[0]
    inst.ireg = operands[1]
    if len(operands) == 3:
      inst.immediate = operands[2]

  def disassemble_operands(self, inst):
    operands = [REGISTER_NAMES[inst.reg]]

    if inst.immediate != 0:
      reg = REGISTER_NAMES[inst.ireg]
      s = '-' if inst.immediate < 0 else ''
      operands.append('%s[%s0x%04X]' % (reg, s, abs(inst.immediate)))

    else:
      operands.append(REGISTER_NAMES[inst.ireg])

    return operands

class InstDescriptor_Generic_Binary_A_R(InstDescriptor):
  operands = 'a,r'
  binary_format = [BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg = operands[-1]
    inst.ireg = operands[0]
    if len(operands) == 3:
      inst.immediate = operands[1]

  def disassemble_operands(self, inst):
    operands = []

    if inst.immediate != 0:
      reg = REGISTER_NAMES[inst.ireg]
      s = '-' if inst.immediate < 0 else ''
      operands.append('%s[%s0x%04X]' % (reg, s, abs(inst.immediate)))

    else:
      operands.append(REGISTER_NAMES[inst.ireg])

    operands.append(REGISTER_NAMES[inst.reg])

    return operands

class InstDescriptor_Generic_Binary_R_R(InstDescriptor):
  operands = 'r,r'
  binary_format = [BF_REG('reg1'), BF_REG('reg2')]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg1 = operands[0]
    inst.reg2 = operands[1]

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg1], REGISTER_NAMES[inst.reg2]]

class Inst_NOP(InstDescriptor_Generic):
  mnemonic = 'nop'
  opcode = Opcodes.NOP


#
# Interrupts
#
class Inst_INT(InstDescriptor_Generic_Unary_RI):
  mnemonic      = 'int'
  opcode        = Opcodes.INT

class Inst_RETINT(InstDescriptor_Generic):
  mnemonic = 'retint'
  opcode   = Opcodes.RETINT

#
# Routines
#
class Inst_CALL(InstDescriptor_Generic_Unary_RI):
  mnemonic      = 'call'
  opcode        = Opcodes.CALL
  relative_address = True

class Inst_RET(InstDescriptor_Generic):
  mnemonic      = 'ret'
  opcode        = Opcodes.RET

#
# CPU
#
class Inst_CLI(InstDescriptor_Generic):
  mnemonic = 'cli'
  opcode = Opcodes.CLI

class Inst_STI(InstDescriptor_Generic):
  mnemonic = 'sti'
  opcode = Opcodes.STI

class Inst_HLT(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'hlt'
  opcode = Opcodes.HLT

class Inst_RST(InstDescriptor_Generic):
  mnemonic = 'rst'
  opcode = Opcodes.RST

class Inst_IDLE(InstDescriptor_Generic):
  mnemonic = 'idle'
  opcode = Opcodes.IDLE

#
# Stack
#
class Inst_PUSH(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'push'
  opcode = Opcodes.PUSH

class Inst_POP(InstDescriptor_Generic_Unary_R):
  mnemonic = 'pop'
  opcode = Opcodes.POP

#
# Arithmetic
#
class Inst_INC(InstDescriptor_Generic_Unary_R):
  mnemonic = 'inc'
  opcode = Opcodes.INC

class Inst_DEC(InstDescriptor_Generic_Unary_R):
  mnemonic = 'dec'
  opcode = Opcodes.DEC

class Inst_ADD(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'add'
  opcode = Opcodes.ADD

class Inst_SUB(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'sub'
  opcode = Opcodes.SUB


#
# Conditional and unconditional jumps
#
class Inst_CMP(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'cmp'
  opcode = Opcodes.CMP

class Inst_CMPU(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'cmpu'
  opcode = Opcodes.CMPU

class Inst_J(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'j'
  opcode   = Opcodes.J
  relative_address = True

class Inst_BE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'be'
  opcode   = Opcodes.BE
  relative_address = True

class Inst_BNE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bne'
  opcode   = Opcodes.BNE
  relative_address = True

class Inst_BNS(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bns'
  opcode   = Opcodes.BNS
  relative_address = True

class Inst_BNZ(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bnz'
  opcode   = Opcodes.BNZ
  relative_address = True

class Inst_BS(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bs'
  opcode   = Opcodes.BS
  relative_address = True

class Inst_BZ(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bz'
  opcode   = Opcodes.BZ
  relative_address = True

class Inst_BG(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bg'
  opcode = Opcodes.BG
  relative_address = True

class Inst_BGE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bge'
  opcode = Opcodes.BGE
  relative_address = True

class Inst_BL(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bl'
  opcode = Opcodes.BL
  relative_address = True

class Inst_BLE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'ble'
  opcode = Opcodes.BLE
  relative_address = True

#
# IO
#
class Inst_IN(InstDescriptor_Generic_Binary_R_RI):
  mnemonic      = 'in'
  opcode        = Opcodes.IN

class Inst_INB(InstDescriptor_Generic_Binary_R_RI):
  mnemonic      = 'inb'
  opcode = Opcodes.INB

class Inst_OUT(InstDescriptor_Generic_Binary_RI_R):
  mnemonic      = 'out'
  opcode        = Opcodes.OUT

class Inst_OUTB(InstDescriptor_Generic_Binary_RI_R):
  mnemonic      = 'outb'
  opcode = Opcodes.OUTB

#
# Bit operations
#
class Inst_AND(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'and'
  opcode = Opcodes.AND

class Inst_OR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'or'
  opcode = Opcodes.OR

class Inst_XOR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'xor'
  opcode = Opcodes.XOR

class Inst_NOT(InstDescriptor_Generic_Unary_R):
  mnemonic = 'not'
  opcode = Opcodes.NOT

class Inst_SHIFTL(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'shiftl'
  opcode = Opcodes.SHIFTL

class Inst_SHIFTR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'shiftr'
  opcode = Opcodes.SHIFTR

#
# Memory load/store operations
#
class Inst_CAS(InstDescriptor):
  operands = 'r,r,r'
  binary_format = [BF_REG('r_addr'), BF_REG('r_test'), BF_REG('r_rep')]

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_addr = operands[0]
    inst.r_test = operands[1]
    inst.r_rep = operands[2]

  def disassemble_operands(self, inst):
    return [
      REGISTER_NAMES[inst.r_addr],
      REGISTER_NAMES[inst.r_test],
      REGISTER_NAMES[inst.r_rep]
    ]

class Inst_LW(InstDescriptor_Generic_Binary_R_A):
  mnemonic = 'lw'
  opcode = Opcodes.LW

class Inst_LB(InstDescriptor_Generic_Binary_R_A):
  mnemonic = 'lb'
  opcode = Opcodes.LB

class Inst_LI(InstDescriptor_Generic_Binary_R_I):
  mnemonic    = 'li'
  opcode = Opcodes.LI

class Inst_STW(InstDescriptor_Generic_Binary_A_R):
  mnemonic    = 'stw'
  opcode = Opcodes.STW

class Inst_STB(InstDescriptor_Generic_Binary_A_R):
  mnemonic    = 'stb'
  opcode = Opcodes.STB

class Inst_MOV(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'mov'
  opcode = Opcodes.MOV

class Inst_SWP(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'swp'
  opcode = Opcodes.SWP

class Inst_MUL(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'mul'
  opcode = Opcodes.MUL

class Inst_DIV(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'div'
  opcode = Opcodes.DIV

class Inst_MOD(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'mod'
  opcode = Opcodes.MOD

INSTRUCTIONS = [
Inst_NOP(),
Inst_INT(),
Inst_RETINT(),
Inst_CALL(),
Inst_RET(),
Inst_CLI(),
Inst_STI(),
Inst_HLT(),
Inst_RST(),
Inst_IDLE(),
Inst_PUSH(),
Inst_POP(),
Inst_INC(),
Inst_DEC(),
Inst_ADD(),
Inst_SUB(),
Inst_CMP(),
Inst_J(),
Inst_BE(),
Inst_BNE(),
Inst_BNS(),
Inst_BNZ(),
Inst_BS(),
Inst_BZ(),
Inst_BG(),
Inst_BGE(),
Inst_BL(),
Inst_BLE(),
Inst_IN(),
Inst_INB(),
Inst_OUT(),
Inst_OUTB(),
Inst_AND(),
Inst_OR(),
Inst_XOR(),
Inst_NOT(),
Inst_SHIFTL(),
Inst_SHIFTR(),
Inst_LW(),
Inst_LB(),
Inst_LI(),
Inst_STW(),
Inst_STB(),
Inst_MOV(),
Inst_SWP(),
Inst_MUL(),
Inst_DIV(),
Inst_MOD(),
Inst_CMPU()
]

def __create_binary_format_master_class():
  fields = [
    ('overall', GenericInstBinaryFormat_Overall),
    ('opcode',  GenericInstBinaryFormat_Opcode)
  ]

  for desc in INSTRUCTIONS:
    fields.append((desc.binary_format_name, desc.binary_format))

  return type('InstBinaryFormat_Master', (ctypes.Union,), {'_pack_': 0, '_fields_': fields})

def __create_opcode_map():
  opcode_map = {}

  for desc in INSTRUCTIONS:
    opcode_map[desc.opcode] = desc

  return opcode_map

InstBinaryFormat_Master = __create_binary_format_master_class()

OPCODE_TO_DESC_MAP = __create_opcode_map()
