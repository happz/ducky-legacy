import collections
import ctypes
import enum
import math
import re

from ctypes import LittleEndianStructure, Union, c_uint, c_int

from util import debug
from mm import UInt32, UInt16, UINT16_FMT, ADDR_FMT
from cpu.registers import Registers

class Opcodes(enum.IntEnum):
  NOP    = 0

  #
  # Memory load/store operations
  #
  LW     =  1
  LB     =  2
  LBU    =  3
  LI     =  4
  STW    =  5
  STB    =  6
  STBU   =  7
  MOV    =  8
  SWP    =  9

  # 2
  INT    = 10
  RETINT = 11

  # 2
  CALL   = 12
  CALLI  = 13
  RET    = 14

  # 5
  CLI    = 15
  STI    = 16
  RST    = 17
  HLT    = 18
  IDLE   = 19

  # 2
  PUSH   = 20
  POP    = 21

  # 4
  INC    = 22
  DEC    = 23
  ADD    = 24
  SUB    = 25
  ADDI   = 26
  SUBI   = 27

  # 6
  AND    = 28
  OR     = 29
  XOR    = 30
  NOT    = 31
  SHIFTL = 32
  SHIFTR = 33

  # 2
  OUT    = 34
  IN     = 35
  OUTB   = 36
  INB    = 37

  # 5
  CMP    = 38
  J      = 39
  JR     = 40
  BE     = 41
  BNE    = 42
  BZ     = 43
  BNZ    = 44
  BS     = 45
  BNS    = 46
  BER    = 47
  BNER   = 48
  BZR    = 49
  BNZR   = 50
  BSR    = 51
  BNSR   = 52

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

PATTERN_REGISTER = r'(?P<common_register_n{register_index}>r(?P<common_register_n{register_index}_number>\d\d?))'
PATTERN_ADDRESS_REGISTER = r'(?P<address_register>(?:r(\d\d?)|(sp)|(fp)))(?:\[(?P<shift>-)?(?P<offset>(?:0x[0-9a-fA-F]+|\d+))\])?'
PATTERN_JUMP_LABEL = r'(?P<jump_label>@[a-zA-Z_][a-zA-Z0-9_-]*)'
PATTERN_IMMEDIATE  = r'(?:(?P<immediate_hex>0x[0-9a-fA-F]+)|(?P<immediate_dec>\d+)|(?P<immediate_data_address>&[a-zA-Z_][a-zA-Z0-9_]*)|(?P<immediate_label>@[a-zA-Z_][a-zA-Z0-9_-]*))'

class InstDescriptor(object):
  mnemonic      = None
  opcode        = None
  operands      = None
  binary_format = None

  pattern       = None
  binary_format_name = None

  def create_binary_format_class(self):
    fields = []

    fields_desc = self.binary_format.split(',') if self.binary_format else []

    if not len(fields_desc) or not fields_desc[0].startswith('opcode'):
      fields_desc.insert(0, 'opcode:6')

    for field in fields_desc:
      field = field.split(':')
      data_type = c_int if len(field) == 3 else c_uint
      fields.append((field[0], data_type, int(field[1])))

    self.binary_format_name = 'InstBinaryFormat_%s' % self.mnemonic
    self.binary_format = type(self.binary_format_name, (ctypes.LittleEndianStructure,), {'_pack_': 0, '_fields_': fields})

  def __init__(self):
    super(InstDescriptor, self).__init__()

    pattern = self.mnemonic

    if self.operands:
      operands = []

      i = 0
      for o in self.operands:
        if   o == 'r':
          operands.append(PATTERN_REGISTER.format(register_index = str(i)))

        elif o == 'R':
          operands.append(PATTERN_ADDRESS_REGISTER)

        elif o == 'j':
          operands.append(PATTERN_JUMP_LABEL)

        elif o == 'i':
          operands.append(PATTERN_IMMEDIATE)

        else:
          raise Exception('Unknown operand %s in %s' % (o, self.__class__))

        i += 1

      pattern += ' ' + ', '.join(operands)

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
      for i in range(0, len(self.operands)):
        operand = self.operands[i]

        # register
        if operand == 'r':
          operands.append(int(raw_match.group('common_register_n%i_number' % i)))

        elif operand == 'R':
          reg = matches['address_register']

          if reg == 'fp':
            reg = Registers.FP
          elif reg == 'sp':
            reg = Registers.SP
          else:
            reg = reg[1:]

          operands.append(reg)

          if 'offset' in matches and matches['offset']:
            k = -1 if 'shift' in matches and matches['shift'] and matches['shift'].strip() == '-' else 1

            if matches['offset'].startswith('0x'):
              operands.append(int(matches['offset'], base = 16) * k)

            else:
              operands.append(int(matches['offset']) * k)

        elif operand == 'j':
          operands.append(matches['jump_label'])

        elif operand == 'i':
          if 'immediate_hex' in matches and matches['immediate_hex']:
            operands.append(str(int(matches['immediate_hex'], base = 16)))

          elif 'immediate_dec' in matches and matches['immediate_dec']:
            operands.append(str(int(matches['immediate_dec'])))

          elif 'immediate_data_address' in matches and matches['immediate_data_address']:
            operands.append(matches['immediate_data_address'])

          elif 'immediate_label' in matches and matches['immediate_label']:
            operands.append(matches['immediate_label'])

          else:
            raise Exception('Unhandled operand')

    else:
      pass

    self.assemble_operands(real, operands)

    for flag in [f for f in dir(self) if f.startswith('flag_')]:
      setattr(real, flag.split('_')[1], getattr(self, flag))

    return real

class Inst_NOP(InstDescriptor):
  mnemonic = 'nop'
  opcode = Opcodes.NOP


#
# Interrupts
#
class Inst_INT(InstDescriptor):
  mnemonic      = 'int'
  opcode        = Opcodes.INT
  operands      = 'r'
  binary_format = 'r_int:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_int = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_int]

class Inst_RETINT(InstDescriptor):
  mnemonic = 'retint'
  opcode   = Opcodes.RETINT

#
# Routines
#
class Inst_CALL(InstDescriptor):
  mnemonic      = 'call'
  opcode        = Opcodes.CALL
  operands      = 'r'
  binary_format = 'r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst]

class Inst_CALLI(InstDescriptor):
  mnemonic      = 'calli'
  opcode        = Opcodes.CALLI
  operands      = 'i'
  binary_format = 'immediate:16'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.immediate = 0
    inst.refers_to = operands[0]

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    return [inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [ADDR_FMT(inst.immediate)]

class Inst_RET(InstDescriptor):
  mnemonic      = 'ret'
  opcode        = Opcodes.RET

#
# CPU
#
class Inst_CLI(InstDescriptor):
  mnemonic = 'cli'
  opcode = Opcodes.CLI

class Inst_STI(InstDescriptor):
  mnemonic = 'sti'
  opcode = Opcodes.STI

class Inst_HLT(InstDescriptor):
  mnemonic = 'hlt'
  opcode = Opcodes.HLT
  operands = 'r'
  binary_format = 'r_code:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_code = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_code]

class Inst_RST(InstDescriptor):
  mnemonic = 'rst'
  opcode = Opcodes.RST

class Inst_IDLE(InstDescriptor):
  mnemonic = 'idle'
  opcode = Opcodes.IDLE

#
# Stack
#
class Inst_PUSH(InstDescriptor):
  mnemonic = 'push'
  opcode = Opcodes.PUSH
  operands = 'r'
  binary_format = 'r_src:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_src = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_src]

class Inst_POP(InstDescriptor):
  mnemonic = 'pop'
  opcode = Opcodes.POP
  operands = 'r'
  binary_format = 'r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst]

#
# Arithmetic
#
class Inst_INC(InstDescriptor):
  mnemonic = 'inc'
  opcode = Opcodes.INC
  operands = 'r'
  binary_format = 'r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst]

class Inst_DEC(InstDescriptor):
  mnemonic = 'dec'
  opcode = Opcodes.DEC
  operands = 'r'
  binary_format = 'r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst]

class Inst_ADD(InstDescriptor):
  mnemonic = 'add'
  opcode = Opcodes.ADD
  operands = 'rr'
  binary_format = 'r_dst:5,r_add:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_add = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_add]

class Inst_SUB(InstDescriptor):
  mnemonic = 'sub'
  opcode = Opcodes.SUB
  operands = 'rr'
  binary_format = 'r_dst:5,r_sub:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_sub = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_sub]

class Inst_ADDI(InstDescriptor):
  mnemonic = 'addi'
  opcode = Opcodes.ADDI
  operands = 'ri'
  binary_format = 'r_dst:5,immediate:16'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_immediate = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, UINT16_FMT(inst.immediate)]

class Inst_SUBI(InstDescriptor):
  mnemonic = 'subi'
  opcode = Opcodes.SUBI
  operands = 'ri'
  binary_format = 'r_dst:5,immediate:16'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.immediate = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, UINT16_FMT(inst.immediate)]

#
# Conditional and unconditional jumps
#
class Inst_CMP(InstDescriptor):
  mnemonic = 'cmp'
  opcode = Opcodes.CMP
  operands = 'rr'
  binary_format = 'reg1:5,reg2:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg1 = int(operands[0])
    inst.reg2 = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.reg1, 'r%i' % inst.reg2]

class Inst_BaseOffsetJump(InstDescriptor):
  operands      = 'j'
  binary_format = 'immediate:16'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.refers_to = operands[0]

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    return [inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [ADDR_FMT(inst.immediate)]

class Inst_J(Inst_BaseOffsetJump):
  mnemonic = 'j'
  opcode   = Opcodes.J

class Inst_BE(Inst_BaseOffsetJump):
  mnemonic = 'be'
  opcode   = Opcodes.BE

class Inst_BNE(Inst_BaseOffsetJump):
  mnemonic = 'bne'
  opcode   = Opcodes.BNE

class Inst_BNS(Inst_BaseOffsetJump):
  mnemonic = 'bns'
  opcode   = Opcodes.BNS

class Inst_BNZ(Inst_BaseOffsetJump):
  mnemonic = 'bnz'
  opcode   = Opcodes.BNZ

class Inst_BS(Inst_BaseOffsetJump):
  mnemonic = 'bs'
  opcode   = Opcodes.BS

class Inst_BZ(Inst_BaseOffsetJump):
  mnemonic = 'bz'
  opcode   = Opcodes.BZ

class Inst_BaseRegisterJump(InstDescriptor):
  operands      = 'r'
  binary_format = 'r_address:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_address = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_address]

class Inst_JR(Inst_BaseRegisterJump):
  mnemonic = 'jr'
  opcode   = Opcodes.JR

class Inst_BER(Inst_BaseRegisterJump):
  mnemonic = 'ber'
  opcode   = Opcodes.BER

class Inst_BNER(Inst_BaseRegisterJump):
  mnemonic = 'bner'
  opcode   = Opcodes.BNER

class Inst_BNSR(Inst_BaseRegisterJump):
  mnemonic = 'bnsr'
  opcode   = Opcodes.BNSR

class Inst_BNZR(Inst_BaseRegisterJump):
  mnemonic = 'bnzr'
  opcode   = Opcodes.BNZR

class Inst_BSR(Inst_BaseRegisterJump):
  mnemonic = 'bsr'
  opcode   = Opcodes.BSR

class Inst_BZR(Inst_BaseRegisterJump):
  mnemonic = 'bzr'
  opcode   = Opcodes.BZR

#
# IO
#
class Inst_IN(InstDescriptor):
  mnemonic      = 'in'
  opcode        = Opcodes.IN
  operands      = 'rr'
  binary_format = 'r_port:5,r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_port = int(operands[0])
    inst.r_dst = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_port, 'r%i' % inst.r_dst]

class Inst_INB(Inst_IN):
  mnemonic      = 'inb'
  opcode = Opcodes.INB

class Inst_OUT(InstDescriptor):
  mnemonic      = 'out'
  opcode        = Opcodes.OUT
  operands      = 'rr'
  binary_format = 'byte:1,r_port:5,r_src:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_port = int(operands[0])
    inst.r_src = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_port, 'r%i' % inst.r_src]

class Inst_OUTB(Inst_OUT):
  mnemonic      = 'outb'
  opcode = Opcodes.OUTB

#
# Bit operations
#
class Inst_AND(InstDescriptor):
  mnemonic = 'and'
  opcode = Opcodes.AND
  operands = 'rr'
  binary_format = 'r_dst:5,r_mask:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_mask = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_mask]

class Inst_OR(InstDescriptor):
  mnemonic = 'or'
  opcode = Opcodes.OR
  operands = 'rr'
  binary_format = 'r_dst:5,r_mask:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_mask = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_mask]

class Inst_XOR(InstDescriptor):
  mnemonic = 'xor'
  opcode = Opcodes.XOR
  operands = 'rr'
  binary_format = 'r_dst:5,r_mask:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_mask = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_mask]

class Inst_NOT(InstDescriptor):
  mnemonic = 'not'
  opcode = Opcodes.NOT
  operands = 'r'
  binary_format = 'r_dst:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst]

class Inst_BaseShift(InstDescriptor):
  operands = 'ri'
  binary_format = 'r_dst:5,immediate:4'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.immediate = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, '%i' % inst.immediate]

class Inst_SHIFTL(Inst_BaseShift):
  mnemonic = 'shiftl'
  opcode = Opcodes.SHIFTL

class Inst_SHIFTR(Inst_BaseShift):
  mnemonic = 'shiftr'
  opcode = Opcodes.SHIFTR

#
# Memory load/store operations
#
class Inst_BaseLoad(InstDescriptor):
  operands = 'rR'
  binary_format = 'r_dst:5,r_address:5,immediate:16:int'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_address = int(operands[1])
    if len(operands) == 3:
      inst.immediate = int(operands[2])

  def disassemble_operands(self, inst):
    operands = ['r%i' % inst.r_dst]

    if inst.immediate != 0:
      if inst.r_address in (Registers.SP, Registers.FP):
        reg = 'sp' if inst.r_address == Registers.SP else 'fp'
      else:
        reg = 'r%i' % inst.r_address

      s = '-' if inst.immediate < 0 else ''
      operands.append('%s[%s0x%04X]' % (reg, s, int(math.fabs(inst.immediate))))

    else:
      if inst.r_address in (Registers.SP, Registers.FP):
        reg = 'sp' if inst.r_address == Registers.SP else 'fp'
      else:
        reg = 'r%i' % inst.r_address

      operands.append(reg)

    return operands

class Inst_LW(Inst_BaseLoad):
  mnemonic = 'lw'
  opcode = Opcodes.LW

class Inst_LB(Inst_BaseLoad):
  mnemonic = 'lb'
  opcode = Opcodes.LB

class Inst_LBU(Inst_BaseLoad):
  mnemonic = 'lbu'
  opcode = Opcodes.LBU

class Inst_LI(Inst_BaseLoad):
  mnemonic    = 'li'
  opcode = Opcodes.LI
  operands = 'ri'
  binary_format = 'r_dst:5,immediate:16'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])

    if operands[1].startswith('&'):
      inst.refers_to = operands[1]
    else:
      inst.immediate = int(operands[1])

  def fix_refers_to(self, inst, refers_to):
    debug('fix_refers_to: inst=%s, refers_to=%s' % (inst, UINT16_FMT(refers_to)))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    r_dst = 'r%i' % inst.r_dst

    return [r_dst, inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [r_dst, UINT16_FMT(inst.immediate)]

class Inst_BaseStore(InstDescriptor):
  operands = 'Rr'
  binary_format = 'r_src:5,r_address:5,immediate:16:int'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[-1])
    inst.r_address = int(operands[0])
    if len(operands) == 3:
      inst.immediate = int(operands[1])

  def disassemble_operands(self, inst):
    operands = []

    if inst.immediate != 0:
      if inst.r_address in (Registers.SP, Registers.FP):
        reg = 'sp' if inst.r_address == Registers.SP else 'fp'
      else:
        reg = 'r%i' % inst.r_address

      s = '-' if inst.immediate < 0 else ''
      operands.append('%s[%s0x%04X]' % (reg, s, int(math.fabs(inst.immediate))))
    else:
      if inst.r_address in (Registers.SP, Registers.FP):
        reg = 'sp' if inst.r_address == Registers.SP else 'fp'

      else:
        reg = 'r%i' % inst.r_address

      operands.append(reg)

    operands.append('r%i' % inst.r_src)

    return operands

class Inst_STW(Inst_BaseStore):
  mnemonic    = 'stw'
  opcode = Opcodes.STW

class Inst_STB(Inst_BaseStore):
  mnemonic    = 'stb'
  opcode = Opcodes.STB

class Inst_STBU(Inst_BaseStore):
  mnemonic = 'stbu'
  opcode = Opcodes.STBU

class Inst_MOV(InstDescriptor):
  mnemonic = 'mov'
  opcode = Opcodes.MOV
  operands = 'rr'
  binary_format = 'r_dst:5,r_src:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.r_dst = int(operands[0])
    inst.r_src = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.r_dst, 'r%i' % inst.r_src]

class Inst_SWP(InstDescriptor):
  mnemonic = 'swp'
  opcode = Opcodes.SWP
  operands = 'rr'
  binary_format = 'reg1:5,reg2:5'

  def assemble_operands(self, inst, operands):
    debug('assemble_operands: inst=%s, operands=%s' % (inst, operands))

    inst.reg1 = int(operands[0])
    inst.reg2 = int(operands[1])

  def disassemble_operands(self, inst):
    return ['r%i' % inst.reg1, 'r%i' % inst.reg2]

INSTRUCTIONS = [
Inst_NOP(),
Inst_INT(),
Inst_RETINT(),
Inst_CALL(),
Inst_CALLI(),
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
Inst_ADDI(),
Inst_SUBI(),
Inst_CMP(),
Inst_J(),
Inst_BE(),
Inst_BNE(),
Inst_BNS(),
Inst_BNZ(),
Inst_BS(),
Inst_BZ(),
Inst_JR(),
Inst_BE(),
Inst_BNE(),
Inst_BNS(),
Inst_BNZ(),
Inst_BS(),
Inst_BZ(),
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
Inst_LBU(),
Inst_LI(),
Inst_STW(),
Inst_STB(),
Inst_STBU(),
Inst_MOV(),
Inst_SWP()
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
