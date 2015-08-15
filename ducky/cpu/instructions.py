import ctypes
import enum
import re
import types

from ctypes import LittleEndianStructure, c_uint, c_int

from .registers import Registers, REGISTER_NAMES
from ..mm import OFFSET_FMT, UINT16_FMT, i16, u16, UInt32

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

PO_REGISTER  = r'(?P<register_n{operand_index}>(?:r\d\d?)|(?:sp)|(?:fp)|(?:ds))'
PO_AREGISTER = r'(?P<address_register>(?:r(\d\d?)|(sp)|(fp)))(?:\[(?P<shift>-)?(?P<offset>(?:0x[0-9a-fA-F]+|\d+))\])?'
PO_IMMEDIATE = r'(?:(?P<immediate_hex>-?0x[0-9a-fA-F]+)|(?P<immediate_dec>-?\d+)|(?P<immediate_address>&[a-zA-Z_\.][a-zA-Z0-9_]*))'


def BF_FLG(n):
  return '{}:1'.format(n)

def BF_REG(*args):
  args = args or ['reg']
  return '{}:4'.format(args[0])

def BF_IMM(*args):
  args = args or ['immediate']
  return '{}:17:int'.format(args[0])


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

    self.binary_format_name = 'InstBinaryFormat_{}'.format(self.mnemonic)
    self.binary_format = type(self.binary_format_name, (ctypes.LittleEndianStructure,), {'_pack_': 0, '_fields_': fields})

    def __repr__(__inst):
      return '<' + self.instruction_set.disassemble_instruction(__inst) + '>'

    self.binary_format.__repr__ = __repr__

  def __init__(self, instruction_set):
    super(InstDescriptor, self).__init__()

    self.instruction_set = instruction_set

    pattern = r'\s*' + self.mnemonic

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
            raise Exception('Unhandled operand type: {}'.format(operand_type))

        operand_patterns.append('(?:' + '|'.join(operand_pattern) + ')')

      pattern += r' ' + ', '.join(operand_patterns)

    pattern = r'^' + pattern + '(?:\s*[;#].*)?$'
    self.pattern = re.compile(pattern, re.MULTILINE)

    self.create_binary_format_class()

    self.instruction_set.instructions.append(self)

  @staticmethod
  def execute(core, inst):
    pass

  def assemble_operands(self, logger, inst, operands):
    pass

  def fix_refers_to(self, logger, inst, refers_to):
    pass

  def fill_reloc_slot(self, logger, inst, slot):
    assert False, 'not implemented in %s' % self.__class__
    pass

  def disassemble_operands(self, inst):
    # pylint: disable-msg=W0613
    return []

  def emit_instruction(self, logger, line):
    DEBUG = logger.debug

    DEBUG('emit_instruction: input line: %s', line)

    master = self.instruction_set.binary_format_master()
    master.overall.u16 = 0

    DEBUG('emit_instruction: binary format is %s', self.binary_format_name)
    DEBUG('emit_instruction: desc is %s', self)

    real = getattr(master, self.binary_format_name)
    real.opcode = self.opcode

    raw_match = self.pattern.match(line)
    matches = raw_match.groupdict()
    DEBUG('emit_instruction: matches=%s', matches)

    operands = []

    if self.operands and len(self.operands):
      for operand_index in range(0, len(self.operands)):
        reg_group_name = 'register_n{}'.format(operand_index)

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
          raise Exception('Unhandled operand: {}'.format(matches))

    else:
      pass

    self.assemble_operands(logger, real, operands)

    for flag in [f for f in dir(self) if f.startswith('flag_')]:
      setattr(real, flag.split('_')[1], getattr(self, flag))

    return real


class InstDescriptor_Generic(InstDescriptor):
  pass

class InstDescriptor_Generic_Unary_R(InstDescriptor):
  operands = 'r'
  binary_format = [BF_REG()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[0]

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg]]


class InstDescriptor_Generic_Unary_I(InstDescriptor):
  operands      = 'i'
  binary_format = [BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    v = operands[0]

    if isinstance(v, types.IntType):
      inst.immediate = v

    elif isinstance(v, types.StringType):
      inst.refers_to = v

  def fix_refers_to(self, logger, inst, refers_to):
    logger.debug('fix_refers_to: inst=%s, refers_to=%s', inst, OFFSET_FMT(refers_to))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Unary_RI(InstDescriptor):
  operands      = 'ri'
  binary_format = [BF_FLG('is_reg'), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    v = operands[0]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif isinstance(v, types.IntType):
      inst.is_reg = 0
      inst.immediate = v

    elif isinstance(v, types.StringType):
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, logger, inst, refers_to):
    logger.debug('fix_refers_to: inst=%s, refers_to=%s', inst, OFFSET_FMT(refers_to))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def fill_reloc_slot(self, logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 11
    slot.patch_size = 17

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_I(InstDescriptor):
  operands = 'r,i'
  binary_format = [BF_REG(), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[0]

    v = operands[1]

    if isinstance(v, types.IntType):
      inst.immediate = v

    else:
      inst.refers_to = v

  def fix_refers_to(self, logger, inst, refers_to):
    logger.debug('fix_refers_to: inst=%s, refers_to=%s', inst, UINT16_FMT(refers_to))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def fill_reloc_slot(self, logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 10
    slot.patch_size = 17

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg], inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [REGISTER_NAMES[inst.reg], OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_RI(InstDescriptor):
  operands = 'r,ri'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[0]

    v = operands[1]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif isinstance(v, types.IntType):
      inst.is_reg = 0
      inst.immediate = v

    elif isinstance(v, types.StringType):
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, logger, inst, refers_to):
    logger.debug('fix_refers_to: inst=%s, refers_to=%s',  inst, UINT16_FMT(refers_to))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def fill_reloc_slot(self, logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 15
    slot.patch_size = 17

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.reg], REGISTER_NAMES[inst.ireg]]

    return [REGISTER_NAMES[inst.reg], inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_RI_R(InstDescriptor):
  operands = 'ri,r'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[1]

    v = operands[0]

    if type(v) == Registers:
      inst.is_reg = 1
      inst.ireg = v

    elif isinstance(v, types.IntType):
      inst.is_reg = 0
      inst.immediate = v

    elif isinstance(v, types.StringType):
      inst.is_reg = 0
      inst.refers_to = v

  def fix_refers_to(self, logger, inst, refers_to):
    logger.debug('fix_refers_to: inst=%s, refers_to=%s', inst, UINT16_FMT(refers_to))

    inst.immediate = int(refers_to)
    inst.refers_to = None

  def disassemble_operands(self, inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg], REGISTER_NAMES[inst.reg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate), REGISTER_NAMES[inst.reg]]

class InstDescriptor_Generic_Binary_R_A(InstDescriptor):
  operands = 'r,a'
  binary_format = [BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[0]
    inst.ireg = operands[1]
    if len(operands) == 3:
      inst.immediate = operands[2]

  def disassemble_operands(self, inst):
    operands = [REGISTER_NAMES[inst.reg]]

    if inst.immediate != 0:
      reg = REGISTER_NAMES[inst.ireg]
      s = '-' if inst.immediate < 0 else ''
      operands.append('{}[{}0x{:04X}]'.format(reg, s, abs(inst.immediate)))

    else:
      operands.append(REGISTER_NAMES[inst.ireg])

    return operands

class InstDescriptor_Generic_Binary_A_R(InstDescriptor):
  operands = 'a,r'
  binary_format = [BF_REG(), BF_REG('ireg'), BF_IMM()]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands[-1]
    inst.ireg = operands[0]
    if len(operands) == 3:
      inst.immediate = operands[1]

  def disassemble_operands(self, inst):
    operands = []

    if inst.immediate != 0:
      reg = REGISTER_NAMES[inst.ireg]
      s = '-' if inst.immediate < 0 else ''
      operands.append('{}[{}0x{:04X}]'.format(reg, s, abs(inst.immediate)))

    else:
      operands.append(REGISTER_NAMES[inst.ireg])

    operands.append(REGISTER_NAMES[inst.reg])

    return operands

class InstDescriptor_Generic_Binary_R_R(InstDescriptor):
  operands = 'r,r'
  binary_format = [BF_REG('reg1'), BF_REG('reg2')]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg1 = operands[0]
    inst.reg2 = operands[1]

  def disassemble_operands(self, inst):
    return [REGISTER_NAMES[inst.reg1], REGISTER_NAMES[inst.reg2]]

class InstructionSetMetaclass(type):
  def __init__(cls, name, bases, dict):
    cls.instructions = []

class InstructionSet(object):
  __metaclass__ = InstructionSetMetaclass

  instruction_set_id = None
  opcodes = None

  @classmethod
  def init(cls):
    if hasattr(cls, 'opcode_desc_map'):
      return

    cls.opcode_desc_map = {}

    for desc in cls.instructions:
      cls.opcode_desc_map[desc.opcode] = desc

    fields = [
      ('overall', GenericInstBinaryFormat_Overall),
      ('opcode',  GenericInstBinaryFormat_Opcode)
    ]

    for desc in cls.instructions:
      fields.append((desc.binary_format_name, desc.binary_format))

    cls.binary_format_master = type('InstBinaryFormat_Master_{}'.format(cls.__name__), (ctypes.Union,), {'_pack_': 0, '_fields_': fields})

  @classmethod
  def convert_to_master(cls, inst):
    if isinstance(inst, cls.binary_format_master):
      return inst

    master = cls.binary_format_master()
    setattr(master, inst.__class__.__name__, inst)
    return master

  @classmethod
  def decode_instruction(cls, inst):
    if isinstance(inst, types.LongType) or isinstance(inst, types.IntType):
      master = cls.binary_format_master()
      master.overall.u32 = inst
      inst = master

    elif isinstance(inst, UInt32):
      master = cls.binary_format_master()
      master.overall.u32 = inst.u32
      inst = master

    if isinstance(inst, cls.binary_format_master):
      if inst.opcode.opcode not in cls.opcode_desc_map:
        from ..cpu import InvalidOpcodeError
        raise InvalidOpcodeError(inst.opcode.opcode)

      return getattr(inst, cls.opcode_desc_map[inst.opcode.opcode].binary_format_name)

    return inst

  @classmethod
  def disassemble_instruction(cls, inst):
    inst = cls.decode_instruction(inst)
    desc = cls.opcode_desc_map[inst.opcode]

    operands = desc.disassemble_operands(inst)

    return (desc.mnemonic + ' ' + ', '.join(operands)) if len(operands) else desc.mnemonic

#
# Main instruction set
#

class DuckyOpcodes(enum.IntEnum):
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

  UDIV   = 52

  CMPU   = 51

  SIS    = 63


class Inst_NOP(InstDescriptor_Generic):
  mnemonic = 'nop'
  opcode = DuckyOpcodes.NOP


#
# Interrupts
#
class Inst_INT(InstDescriptor_Generic_Unary_RI):
  mnemonic      = 'int'
  opcode        = DuckyOpcodes.INT

  @staticmethod
  def execute(core, inst):
    core.do_int(core.RI_VAL(inst))

class Inst_RETINT(InstDescriptor_Generic):
  mnemonic = 'retint'
  opcode   = DuckyOpcodes.RETINT

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.exit_interrupt()

#
# Routines
#
class Inst_CALL(InstDescriptor_Generic_Unary_RI):
  mnemonic      = 'call'
  opcode        = DuckyOpcodes.CALL
  relative_address = True

  @staticmethod
  def execute(core, inst):
    core.create_frame()

    core.JUMP(inst)

    if core.check_frames:
      core.frames[-1].IP = core.registers.ip.value

class Inst_RET(InstDescriptor_Generic):
  mnemonic      = 'ret'
  opcode        = DuckyOpcodes.RET

  @staticmethod
  def execute(core, inst):
    core.destroy_frame()

#
# CPU
#
class Inst_CLI(InstDescriptor_Generic):
  mnemonic = 'cli'
  opcode = DuckyOpcodes.CLI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.registers.flags.hwint = 0

class Inst_STI(InstDescriptor_Generic):
  mnemonic = 'sti'
  opcode = DuckyOpcodes.STI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.registers.flags.hwint = 1

class Inst_HLT(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'hlt'
  opcode = DuckyOpcodes.HLT

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.exit_code = core.RI_VAL(inst)
    core.halt()

class Inst_RST(InstDescriptor_Generic):
  mnemonic = 'rst'
  opcode = DuckyOpcodes.RST

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.reset()

class Inst_IDLE(InstDescriptor_Generic):
  mnemonic = 'idle'
  opcode = DuckyOpcodes.IDLE

  @staticmethod
  def execute(core, inst):
    core.idle = True

class Inst_SIS(InstDescriptor_Generic_Unary_I):
  mnemonic = 'sis'
  opcode = DuckyOpcodes.SIS

  @staticmethod
  def execute(core, inst):
    core.instruction_set = get_instruction_set(inst.immediate)

#
# Stack
#
class Inst_PUSH(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'push'
  opcode = DuckyOpcodes.PUSH

  @staticmethod
  def execute(core, inst):
    core.raw_push(core.RI_VAL(inst))

class Inst_POP(InstDescriptor_Generic_Unary_R):
  mnemonic = 'pop'
  opcode = DuckyOpcodes.POP

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.pop(inst.reg)
    core.update_arith_flags(core.registers.map[inst.reg])

#
# Arithmetic
#
class Inst_INC(InstDescriptor_Generic_Unary_R):
  mnemonic = 'inc'
  opcode = DuckyOpcodes.INC

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value += 1
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_DEC(InstDescriptor_Generic_Unary_R):
  mnemonic = 'dec'
  opcode = DuckyOpcodes.DEC

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value -= 1
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_ADD(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'add'
  opcode = DuckyOpcodes.ADD

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    v = core.registers.map[inst.reg].value + core.RI_VAL(inst)
    core.registers.map[inst.reg].value += core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

    if v > 0xFFFF:
      core.registers.flags.o = 1

class Inst_SUB(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'sub'
  opcode = DuckyOpcodes.SUB

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    v = core.RI_VAL(inst) > core.registers.map[inst.reg].value
    core.registers.map[inst.reg].value -= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

    if v:
      core.registers.flags.s = 1

#
# Conditional and unconditional jumps
#
class Inst_CMP(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'cmp'
  opcode = DuckyOpcodes.CMP

  @staticmethod
  def execute(core, inst):
    core.CMP(core.registers.map[inst.reg].value, core.RI_VAL(inst))

class Inst_CMPU(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'cmpu'
  opcode = DuckyOpcodes.CMPU

  @staticmethod
  def execute(core, inst):
    core.CMP(core.registers.map[inst.reg].value, core.RI_VAL(inst), signed = False)

class Inst_J(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'j'
  opcode   = DuckyOpcodes.J
  relative_address = True

  @staticmethod
  def execute(core, inst):
    core.JUMP(inst)

class Inst_BE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'be'
  opcode   = DuckyOpcodes.BE
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.e == 1:
      core.JUMP(inst)

class Inst_BNE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bne'
  opcode   = DuckyOpcodes.BNE
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.e == 0:
      core.JUMP(inst)

class Inst_BNS(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bns'
  opcode   = DuckyOpcodes.BNS
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 0:
      core.JUMP(inst)

class Inst_BNZ(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bnz'
  opcode   = DuckyOpcodes.BNZ
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.z == 0:
      core.JUMP(inst)

class Inst_BS(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bs'
  opcode   = DuckyOpcodes.BS
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 1:
      core.JUMP(inst)

class Inst_BZ(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bz'
  opcode   = DuckyOpcodes.BZ
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.z == 1:
      core.JUMP(inst)

class Inst_BG(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bg'
  opcode = DuckyOpcodes.BG
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 0 and core.registers.flags.e == 0:
      core.JUMP(inst)

class Inst_BGE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bge'
  opcode = DuckyOpcodes.BGE
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 0 or core.registers.flags.e == 1:
      core.JUMP(inst)

class Inst_BL(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'bl'
  opcode = DuckyOpcodes.BL
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 1 and core.registers.flags.e == 0:
      core.JUMP(inst)

class Inst_BLE(InstDescriptor_Generic_Unary_RI):
  mnemonic = 'ble'
  opcode = DuckyOpcodes.BLE
  relative_address = True

  @staticmethod
  def execute(core, inst):
    if core.registers.flags.s == 1 or core.registers.flags.e == 1:
      core.JUMP(inst)

#
# IO
#
class Inst_IN(InstDescriptor_Generic_Binary_R_RI):
  mnemonic      = 'in'
  opcode        = DuckyOpcodes.IN

  @staticmethod
  def execute(core, inst):
    port = core.RI_VAL(inst)
    core.check_protected_port(port)
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = core.cpu.machine.ports[port].read_u16(port)

class Inst_INB(InstDescriptor_Generic_Binary_R_RI):
  mnemonic      = 'inb'
  opcode = DuckyOpcodes.INB

  @staticmethod
  def execute(core, inst):
    port = core.RI_VAL(inst)
    core.check_protected_port(port)
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = core.cpu.machine.ports[port].read_u8(port)
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_OUT(InstDescriptor_Generic_Binary_RI_R):
  mnemonic      = 'out'
  opcode        = DuckyOpcodes.OUT

  @staticmethod
  def execute(core, inst):
    port = core.RI_VAL(inst)
    core.check_protected_port(port)
    core.cpu.machine.ports[port].write_u16(port, core.registers.map[inst.reg].value)

class Inst_OUTB(InstDescriptor_Generic_Binary_RI_R):
  mnemonic      = 'outb'
  opcode = DuckyOpcodes.OUTB

  @staticmethod
  def execute(core, inst):
    port = core.RI_VAL(inst)
    core.check_protected_port(port)
    core.cpu.machine.ports[port].write_u8(port, core.registers.map[inst.reg].value & 0xFF)

#
# Bit operations
#
class Inst_AND(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'and'
  opcode = DuckyOpcodes.AND

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value &= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_OR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'or'
  opcode = DuckyOpcodes.OR

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value |= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_XOR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'xor'
  opcode = DuckyOpcodes.XOR

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value ^= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_NOT(InstDescriptor_Generic_Unary_R):
  mnemonic = 'not'
  opcode = DuckyOpcodes.NOT

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = ~core.registers.map[inst.reg].value
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_SHIFTL(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'shiftl'
  opcode = DuckyOpcodes.SHIFTL

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value <<= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_SHIFTR(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'shiftr'
  opcode = DuckyOpcodes.SHIFTR

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value >>= core.RI_VAL(inst)
    core.update_arith_flags(core.registers.map[inst.reg])

#
# Memory load/store operations
#
class Inst_CAS(InstDescriptor):
  mnemonic = 'cas'
  opcode = DuckyOpcodes.CAS

  operands = 'r,r,r'
  binary_format = [BF_REG('r_addr'), BF_REG('r_test'), BF_REG('r_rep')]

  def assemble_operands(self, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.r_addr = operands[0]
    inst.r_test = operands[1]
    inst.r_rep = operands[2]

  def disassemble_operands(self, inst):
    return [
      REGISTER_NAMES[inst.r_addr],
      REGISTER_NAMES[inst.r_test],
      REGISTER_NAMES[inst.r_rep]
    ]

  @staticmethod
  def execute(core, inst):
    core.registers.flags.e = 0

    addr = core.DS_ADDR(core.registers.map[inst.r_addr].value)
    value = core.MEM_IN16(addr)

    if value == core.registers.map[inst.r_test].value:
      core.MEM_OUT16(addr, core.registers.map[inst.r_rep].value)
      core.registers.flags.e = 1

    else:
      core.registers.map[inst.r_test].value = value

class Inst_LW(InstDescriptor_Generic_Binary_R_A):
  mnemonic = 'lw'
  opcode = DuckyOpcodes.LW

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = core.data_cache.read_u16(core.OFFSET_ADDR(inst))
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_LB(InstDescriptor_Generic_Binary_R_A):
  mnemonic = 'lb'
  opcode = DuckyOpcodes.LB

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = core.memory.read_u8(core.OFFSET_ADDR(inst))
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_LI(InstDescriptor_Generic_Binary_R_I):
  mnemonic    = 'li'
  opcode = DuckyOpcodes.LI

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = inst.immediate
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_STW(InstDescriptor_Generic_Binary_A_R):
  mnemonic    = 'stw'
  opcode = DuckyOpcodes.STW

  @staticmethod
  def execute(core, inst):
    core.data_cache.write_u16(core.OFFSET_ADDR(inst), core.registers.map[inst.reg].value)

class Inst_STB(InstDescriptor_Generic_Binary_A_R):
  mnemonic    = 'stb'
  opcode = DuckyOpcodes.STB

  @staticmethod
  def execute(core, inst):
    addr = core.OFFSET_ADDR(inst)

    core.cache_controller.release_entry_references(None, (addr + 1) & (~1))
    core.memory.write_u8(core.OFFSET_ADDR(inst), core.registers.map[inst.reg].value & 0xFF)

class Inst_MOV(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'mov'
  opcode = DuckyOpcodes.MOV

  @staticmethod
  def execute(core, inst):
    core.registers.map[inst.reg1].value = core.registers.map[inst.reg2].value

class Inst_SWP(InstDescriptor_Generic_Binary_R_R):
  mnemonic = 'swp'
  opcode = DuckyOpcodes.SWP

  @staticmethod
  def execute(core, inst):
    v = core.registers.map[inst.reg1].value
    core.registers.map[inst.reg1].value = core.registers.map[inst.reg2].value
    core.registers.map[inst.reg2].value = v

class Inst_MUL(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'mul'
  opcode = DuckyOpcodes.MUL

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    r = core.registers.map[inst.reg]
    x = i16(r.value).value
    y = i16(core.RI_VAL(inst)).value
    r.value = x * y
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_DIV(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'div'
  opcode = DuckyOpcodes.DIV

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    r = core.registers.map[inst.reg]
    x = i16(r.value).value
    y = i16(core.RI_VAL(inst)).value

    if abs(y) > abs(x):
      r.value = 0

    else:
      r.value = x / y

    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_UDIV(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'udiv'
  opcode = DuckyOpcodes.UDIV

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    r = core.registers.map[inst.reg]
    x = u16(r.value).value
    y = u16(core.RI_VAL(inst)).value

    r.value = x / y

    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_MOD(InstDescriptor_Generic_Binary_R_RI):
  mnemonic = 'mod'
  opcode = DuckyOpcodes.MOD

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    r = core.registers.map[inst.reg]
    x = i16(r.value).value
    y = i16(core.RI_VAL(inst)).value
    r.value = x % y
    core.update_arith_flags(core.registers.map[inst.reg])

class DuckyInstructionSet(InstructionSet):
  instruction_set_id = 0
  opcodes = DuckyOpcodes

Inst_NOP(DuckyInstructionSet)
Inst_INT(DuckyInstructionSet)
Inst_RETINT(DuckyInstructionSet)
Inst_CALL(DuckyInstructionSet)
Inst_RET(DuckyInstructionSet)
Inst_CLI(DuckyInstructionSet)
Inst_STI(DuckyInstructionSet)
Inst_HLT(DuckyInstructionSet)
Inst_RST(DuckyInstructionSet)
Inst_IDLE(DuckyInstructionSet)
Inst_PUSH(DuckyInstructionSet)
Inst_POP(DuckyInstructionSet)
Inst_INC(DuckyInstructionSet)
Inst_DEC(DuckyInstructionSet)
Inst_ADD(DuckyInstructionSet)
Inst_SUB(DuckyInstructionSet)
Inst_CMP(DuckyInstructionSet)
Inst_J(DuckyInstructionSet)
Inst_BE(DuckyInstructionSet)
Inst_BNE(DuckyInstructionSet)
Inst_BNS(DuckyInstructionSet)
Inst_BNZ(DuckyInstructionSet)
Inst_BS(DuckyInstructionSet)
Inst_BZ(DuckyInstructionSet)
Inst_BG(DuckyInstructionSet)
Inst_BGE(DuckyInstructionSet)
Inst_BL(DuckyInstructionSet)
Inst_BLE(DuckyInstructionSet)
Inst_IN(DuckyInstructionSet)
Inst_INB(DuckyInstructionSet)
Inst_OUT(DuckyInstructionSet)
Inst_OUTB(DuckyInstructionSet)
Inst_AND(DuckyInstructionSet)
Inst_OR(DuckyInstructionSet)
Inst_XOR(DuckyInstructionSet)
Inst_NOT(DuckyInstructionSet)
Inst_SHIFTL(DuckyInstructionSet)
Inst_SHIFTR(DuckyInstructionSet)
Inst_LW(DuckyInstructionSet)
Inst_LB(DuckyInstructionSet)
Inst_LI(DuckyInstructionSet)
Inst_STW(DuckyInstructionSet)
Inst_STB(DuckyInstructionSet)
Inst_MOV(DuckyInstructionSet)
Inst_SWP(DuckyInstructionSet)
Inst_MUL(DuckyInstructionSet)
Inst_DIV(DuckyInstructionSet)
Inst_UDIV(DuckyInstructionSet)
Inst_MOD(DuckyInstructionSet)
Inst_CMPU(DuckyInstructionSet)
Inst_CAS(DuckyInstructionSet)
Inst_SIS(DuckyInstructionSet)

DuckyInstructionSet.init()

INSTRUCTION_SETS = {
  DuckyInstructionSet.instruction_set_id: DuckyInstructionSet
}

def get_instruction_set(i, exc = None):
  from ..cpu import InvalidInstructionSetError
  exc = exc or InvalidInstructionSetError

  if i not in INSTRUCTION_SETS:
    raise exc(i)

  return INSTRUCTION_SETS[i]
