import ctypes
import enum
import re

from six import integer_types, string_types, add_metaclass
from six.moves import range

from ctypes import LittleEndianStructure, c_uint, c_int

from .registers import Registers, REGISTER_NAMES
from ..mm import OFFSET_FMT, i16, u16, UInt32
from ..util import str2int

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
PO_AREGISTER = r'(?P<address_register>r\d\d?|sp|fp|ds)(?:(?P<pointer>\[|\()(?:(?P<immediate_sign>-|\+)?(?P<offset_immediate>0x[0-9a-fA-F]+|\d+)|(?P<offset_register>r\d\d?|sp|fp|ds))(?:\]|\)))?'
PO_IMMEDIATE = r'(?:(?P<immediate>(?:-|\+)?(?:0x[0-9a-fA-F]+|\d+))|(?P<immediate_address>&[a-zA-Z_\.][a-zA-Z0-9_]*))'


def BF_FLG(n):
  return '{}:1'.format(n)

def BF_REG(*args):
  args = args or ['reg']
  return '{}:4'.format(args[0])

def BF_IMM(*args):
  args = args or ['immediate']
  return '{}:17:int'.format(args[0])

def BF_IMM_SHORT(*args):
  args = args or ['immediate']
  return '{}:12:int'.format(args[0])

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

      for operand_index, operand_types in zip(list(range(0, len(self.operands))), self.operands):
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

  @staticmethod
  def assemble_operands(logger, inst, operands):
    pass

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    raise NotImplementedError('Instruction descriptor does not support relocation')

  @staticmethod
  def disassemble_operands(inst):
    return []

  @classmethod
  def disassemble_mnemonic(cls, inst):
    return cls.mnemonic

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

    operands = {}

    def str2reg(r):
      if r == 'sp':
        return Registers.SP
      if r == 'ds':
        return Registers.DS
      if r == 'fp':
        return Registers.FP
      return Registers(int(r[1:]))

    if self.operands and len(self.operands):
      for operand_index in range(0, len(self.operands)):
        reg_group_name = 'register_n{}'.format(operand_index)

        if reg_group_name in matches and matches[reg_group_name]:
          operands[reg_group_name] = str2reg(matches[reg_group_name])

        elif 'address_register' in matches and matches['address_register']:
          operands['areg'] = str2reg(matches['address_register'])

          if 'pointer' in matches and matches['pointer'] is not None:
            if matches['pointer'] == '[':
              operands['pointer'] = 'offset'

            elif matches['pointer'] == '(':
              operands['pointer'] = 'segment'

            else:
              raise Exception('Unhandled pointer type: {}'.format(matches))

          if 'offset_register' in matches and matches['offset_register'] is not None:
            operands['offset_register'] = str2reg(matches['offset_register'])

          elif 'offset_immediate' in matches and matches['offset_immediate'] is not None:
            k = -1 if 'immediate_sign' in matches and matches['immediate_sign'] and matches['immediate_sign'].strip() == '-' else 1
            operands['offset_immediate'] = k * str2int(matches['offset_immediate'])

        elif 'immediate' in matches and matches['immediate']:
          operands['immediate'] = str2int(matches['immediate'])

        elif 'immediate_address' in matches and matches['immediate_address'] is not None:
          operands['immediate'] = matches['immediate_address']

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

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n0']

  @staticmethod
  def disassemble_operands(inst):
    return [REGISTER_NAMES[inst.reg]]


class InstDescriptor_Generic_Unary_I(InstDescriptor):
  operands      = 'i'
  binary_format = [BF_IMM()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    v = operands['immediate']

    if isinstance(v, integer_types):
      inst.immediate = v

    elif isinstance(v, string_types):
      inst.refers_to = v

  @staticmethod
  def disassemble_operands(inst):
    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Unary_RI(InstDescriptor):
  operands      = 'ri'
  binary_format = [BF_FLG('is_reg'), BF_REG('ireg'), BF_IMM()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    if 'register_n0' in operands:
      inst.ireg = operands['register_n0']
      inst.is_reg = 1

    else:
      v = operands['immediate']

      inst.is_reg = 0

      if isinstance(v, integer_types):
        inst.immediate = v

      elif isinstance(v, string_types):
        inst.refers_to = v

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 11
    slot.patch_size = 17

  @staticmethod
  def disassemble_operands(inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_I(InstDescriptor):
  operands = 'r,i'
  binary_format = [BF_REG(), BF_IMM()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n0']

    v = operands['immediate']
    if isinstance(v, integer_types):
      inst.immediate = v

    else:
      inst.refers_to = v

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 10
    slot.patch_size = 17

  @staticmethod
  def disassemble_operands(inst):
    return [REGISTER_NAMES[inst.reg], inst.refers_to] if hasattr(inst, 'refers_to') and inst.refers_to else [REGISTER_NAMES[inst.reg], OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_R_RI(InstDescriptor):
  operands = 'r,ri'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n0']

    if 'register_n1' in operands:
      inst.ireg = operands['register_n1']
      inst.is_reg = 1

    else:
      inst.is_reg = 0

      v = operands['immediate']

      if isinstance(v, integer_types):
        inst.immediate = v

      elif isinstance(v, string_types):
        inst.refers_to = v

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 15
    slot.patch_size = 17

  @staticmethod
  def disassemble_operands(inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.reg], REGISTER_NAMES[inst.ireg]]

    return [REGISTER_NAMES[inst.reg], inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

class InstDescriptor_Generic_Binary_RI_R(InstDescriptor):
  operands = 'ri,r'
  binary_format = [BF_FLG('is_reg'), BF_REG(), BF_REG('ireg'), BF_IMM()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n1']

    if 'register_n0' in operands:
      inst.ireg = operands['register_n0']
      inst.is_reg = 1

    else:
      inst.is_reg = 0

      v = operands['immediate']

      if isinstance(v, integer_types):
        inst.immediate = v

      elif isinstance(v, string_types):
        inst.refers_to = v

  @staticmethod
  def disassemble_operands(inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg], REGISTER_NAMES[inst.reg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate), REGISTER_NAMES[inst.reg]]

class InstDescriptor_Generic_Binary_R_A(InstDescriptor):
  operands = 'r,a'
  binary_format = [BF_FLG('is_reg'), BF_FLG('is_segment'), BF_REG(), BF_REG('areg'), BF_REG('oreg'), BF_IMM_SHORT()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n0']
    inst.areg = operands['areg']

    inst.is_reg = 0
    inst.is_segment = 0

    if 'offset_register' in operands:
      inst.oreg = operands['offset_register']
      inst.is_reg = 1

    elif 'offset_immediate' in operands:
      inst.immediate = operands['offset_immediate']

    if 'pointer' in operands and operands['pointer'] == 'segment':
      inst.is_segment = 1

  @staticmethod
  def disassemble_operands(inst):
    operands = [REGISTER_NAMES[inst.reg]]

    if inst.is_reg == 1:
      p = '()' if inst.is_segment == 1 else '[]'
      operands.append('{}{}{}{}'.format(REGISTER_NAMES[inst.areg], p[0], REGISTER_NAMES[inst.oreg], p[1]))

    else:
      if inst.immediate == 0:
        operands.append(REGISTER_NAMES[inst.areg])

      else:
        s = '-' if inst.immediate < 0 else ''
        p = '()' if inst.is_segment == 1 else '[]'
        operands.append('{}{}{}{}{}'.format(REGISTER_NAMES[inst.areg], p[0], s, abs(inst.immediate), p[1]))

    return operands

class InstDescriptor_Generic_Binary_A_R(InstDescriptor):
  operands = 'a,r'
  binary_format = [BF_FLG('is_reg'), BF_FLG('is_segment'), BF_REG(), BF_REG('areg'), BF_REG('oreg'), BF_IMM_SHORT()]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n1']
    inst.areg = operands['areg']

    inst.is_reg = 0
    inst.is_segment = 0

    if 'offset_register' in operands:
      inst.oreg = operands['offset_register']
      inst.is_reg = 1

    elif 'offset_immediate' in operands:
      inst.immediate = operands['offset_immediate']

    if 'pointer' in operands and operands['pointer'] == 'segment':
      inst.is_segment = 1

  @staticmethod
  def disassemble_operands(inst):
    operands = []

    if inst.reg == 1:
      p = '()' if inst.is_segment == 1 else '[]'
      operands.append('{}{}{}{}'.format(REGISTER_NAMES[inst.areg], p[0], REGISTER_NAMES[inst.oreg], p[1]))

    else:
      if inst.immediate == 0:
        operands.append(REGISTER_NAMES[inst.areg])

      else:
        s = '-' if inst.immediate < 0 else ''
        p = '()' if inst.is_segment == 1 else '[]'
        operands.append('{}{}{}{}{}'.format(REGISTER_NAMES[inst.areg], p[0], s, abs(inst.immediate), p[1]))

    operands.append(REGISTER_NAMES[inst.reg])

    return operands

class InstDescriptor_Generic_Binary_R_R(InstDescriptor):
  operands = 'r,r'
  binary_format = [BF_REG('reg1'), BF_REG('reg2')]

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg1 = operands['register_n0']
    inst.reg2 = operands['register_n1']

  @staticmethod
  def disassemble_operands(inst):
    return [REGISTER_NAMES[inst.reg1], REGISTER_NAMES[inst.reg2]]

class InstructionSetMetaclass(type):
  def __init__(cls, name, bases, dict):
    cls.instructions = []

@add_metaclass(InstructionSetMetaclass)
class InstructionSet(object):
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
    if isinstance(inst, integer_types):
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

    mnemonic = desc.disassemble_mnemonic(inst)
    operands = desc.disassemble_operands(inst)

    return (mnemonic + ' ' + ', '.join(operands)) if operands else mnemonic

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
  DIV    = 49
  MOD    = 50

  UDIV   = 52

  CMPU   = 51

  # B* instructions
  BRANCH = 39
  BE     = 39
  BNE    = 39
  BZ     = 39
  BNZ    = 39
  BO     = 39
  BNO    = 39
  BS     = 39
  BNS    = 39
  BG     = 39
  BGE    = 39
  BL     = 39
  BLE    = 39

  # SET* instructions
  SET    =  7  # master opcode
  SETE   =  7
  SETNE  =  7
  SETZ   =  7
  SETNZ  =  7
  SETO   =  7
  SETNO  =  7
  SETS   =  7
  SETNS  =  7
  SETL   =  7
  SETLE  =  7
  SETG   =  7
  SETGE  =  7

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
    core.change_runnable_state(idle = True)

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
class InstDescriptor_COND(InstDescriptor):
  binary_format = ['flag:3', BF_FLG('value')]

  FLAGS = ['e', 'z', 'o', 's', 'l', 'g']
  GFLAGS = [0, 1, 2, 3]

  @staticmethod
  def set_condition(inst, flag, value):
    inst.flag = InstDescriptor_COND.FLAGS.index(flag)
    inst.value = 1 if value is True else 0

  @staticmethod
  def evaluate(core, inst):
    # genuine flags
    if inst.flag in InstDescriptor_COND.GFLAGS and inst.value == getattr(core.registers.flags, InstDescriptor_SET.FLAGS[inst.flag]):
      return True

    # "less than" flag
    if inst.flag == 4:
      if inst.value == 1 and core.registers.flags.s == 1 and core.registers.flags.e == 0:
        return True

      if inst.value == 0 and (core.registers.flags.s == 0 or core.registers.flags.e == 1):
        return True

    # "greater than" flag
    if inst.flag == 5:
      if inst.value == 1 and core.registers.flags.s == 0 and core.registers.flags.e == 0:
        return True

      if inst.value == 0 and (core.registers.flags.s == 1 or core.registers.flags.e == 1):
        return True

    return False

class InstDescriptor_BRANCH(InstDescriptor_COND):
  operands = 'ri'
  binary_format = InstDescriptor_COND.binary_format + [BF_FLG('is_reg'), BF_REG('ireg'), BF_IMM()]
  relative_address = True

  @classmethod
  def assemble_operands(cls, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    if 'register_n0' in operands:
      inst.ireg = operands['register_n0']
      inst.is_reg = 1

    else:
      v = operands['immediate']

      inst.is_reg = 0

      if isinstance(v, integer_types):
        inst.immediate = v

      elif isinstance(v, string_types):
        inst.refers_to = v

    if cls is Inst_BE:
      InstDescriptor_COND.set_condition(inst, 'e', True)

    elif cls is Inst_BNE:
      InstDescriptor_COND.set_condition(inst, 'e', False)

    elif cls is Inst_BZ:
      InstDescriptor_COND.set_condition(inst, 'z', True)

    elif cls is Inst_BNZ:
      InstDescriptor_COND.set_condition(inst, 'z', False)

    elif cls is Inst_BO:
      InstDescriptor_COND.set_condition(inst, 'o', True)

    elif cls is Inst_BNO:
      InstDescriptor_COND.set_condition(inst, 'o', False)

    elif cls is Inst_BS:
      InstDescriptor_COND.set_condition(inst, 's', True)

    elif cls is Inst_BNS:
      InstDescriptor_COND.set_condition(inst, 's', False)

    elif cls is Inst_BL:
      InstDescriptor_COND.set_condition(inst, 'l', True)

    elif cls is Inst_BLE:
      InstDescriptor_COND.set_condition(inst, 'g', False)

    elif cls is Inst_BG:
      InstDescriptor_COND.set_condition(inst, 'g', True)

    elif cls is Inst_BGE:
      InstDescriptor_COND.set_condition(inst, 'l', False)

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 15
    slot.patch_size = 17

  @staticmethod
  def disassemble_operands(inst):
    if inst.is_reg == 1:
      return [REGISTER_NAMES[inst.ireg]]

    return [inst.refers_to if hasattr(inst, 'refers_to') and inst.refers_to else OFFSET_FMT(inst.immediate)]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in InstDescriptor_COND.GFLAGS:
      return 'b%s%s' % ('n' if inst.value == 0 else '', InstDescriptor_SET.FLAGS[inst.flag])

    else:
      if inst.flag == InstDescriptor_COND.FLAGS.index('l'):
        return 'bl' if inst.value == 1 else 'bge'

      elif inst.flag == InstDescriptor_COND.FLAGS.index('g'):
        return 'bg' if inst.value == 1 else 'ble'

  @staticmethod
  def execute(core, inst):
    if InstDescriptor_COND.evaluate(core, inst):
      core.JUMP(inst)

class InstDescriptor_SET(InstDescriptor_COND):
  operands = 'r'
  binary_format = InstDescriptor_COND.binary_format + [BF_REG('reg')]

  @classmethod
  def assemble_operands(cls, logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.reg = operands['register_n0']

    if cls is Inst_SETE:
      InstDescriptor_COND.set_condition(inst, 'e', True)

    elif cls is Inst_SETNE:
      InstDescriptor_COND.set_condition(inst, 'e', False)

    elif cls is Inst_SETZ:
      InstDescriptor_COND.set_condition(inst, 'z', True)

    elif cls is Inst_SETNZ:
      InstDescriptor_COND.set_condition(inst, 'z', False)

    elif cls is Inst_SETO:
      InstDescriptor_COND.set_condition(inst, 'o', True)

    elif cls is Inst_SETNO:
      InstDescriptor_COND.set_condition(inst, 'o', False)

    elif cls is Inst_SETS:
      InstDescriptor_COND.set_condition(inst, 's', True)

    elif cls is Inst_SETNS:
      InstDescriptor_COND.set_condition(inst, 's', False)

    elif cls is Inst_SETL:
      InstDescriptor_COND.set_condition(inst, 'l', True)

    elif cls is Inst_SETLE:
      InstDescriptor_COND.set_condition(inst, 'g', False)

    elif cls is Inst_SETG:
      InstDescriptor_COND.set_condition(inst, 'g', True)

    elif cls is Inst_SETGE:
      InstDescriptor_COND.set_condition(inst, 'l', False)

  @staticmethod
  def disassemble_operands(inst):
    return [REGISTER_NAMES[inst.reg]]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in InstDescriptor_COND.GFLAGS:
      return 'set%s%s' % ('n' if inst.value == 0 else '', InstDescriptor_SET.FLAGS[inst.flag])

    else:
      return 'set%s%s' % (InstDescriptor_SET.FLAGS[inst.flag], 'e' if inst.value == 1 else '')

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = 1 if InstDescriptor_COND.evaluate(core, inst) is True else 0
    core.update_arith_flags(core.registers.map[inst.reg])

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

class Inst_BE(InstDescriptor_BRANCH):
  mnemonic = 'be'
  opcode   = DuckyOpcodes.BE

class Inst_BNE(InstDescriptor_BRANCH):
  mnemonic = 'bne'
  opcode   = DuckyOpcodes.BNE

class Inst_BNS(InstDescriptor_BRANCH):
  mnemonic = 'bns'
  opcode   = DuckyOpcodes.BNS

class Inst_BNZ(InstDescriptor_BRANCH):
  mnemonic = 'bnz'
  opcode   = DuckyOpcodes.BNZ

class Inst_BS(InstDescriptor_BRANCH):
  mnemonic = 'bs'
  opcode   = DuckyOpcodes.BS

class Inst_BZ(InstDescriptor_BRANCH):
  mnemonic = 'bz'
  opcode   = DuckyOpcodes.BZ

class Inst_BO(InstDescriptor_BRANCH):
  mnemonic = 'bo'
  opcode   = DuckyOpcodes.BO

class Inst_BNO(InstDescriptor_BRANCH):
  mnemonic = 'bno'
  opcode   = DuckyOpcodes.BNO

class Inst_BG(InstDescriptor_BRANCH):
  mnemonic = 'bg'
  opcode = DuckyOpcodes.BG

class Inst_BGE(InstDescriptor_BRANCH):
  mnemonic = 'bge'
  opcode = DuckyOpcodes.BGE

class Inst_BL(InstDescriptor_BRANCH):
  mnemonic = 'bl'
  opcode = DuckyOpcodes.BL

class Inst_BLE(InstDescriptor_BRANCH):
  mnemonic = 'ble'
  opcode = DuckyOpcodes.BLE

class Inst_SETE(InstDescriptor_SET):
  mnemonic = 'sete'
  opcode = DuckyOpcodes.SETE

class Inst_SETNE(InstDescriptor_SET):
  mnemonic = 'setne'
  opcode = DuckyOpcodes.SETNE

class Inst_SETZ(InstDescriptor_SET):
  mnemonic = 'setz'
  opcode = DuckyOpcodes.SETZ

class Inst_SETNZ(InstDescriptor_SET):
  mnemonic = 'setnz'
  opcode = DuckyOpcodes.SETNZ

class Inst_SETO(InstDescriptor_SET):
  mnemonic = 'seto'
  opcode = DuckyOpcodes.SETO

class Inst_SETNO(InstDescriptor_SET):
  mnemonic = 'setno'
  opcode = DuckyOpcodes.SETNO

class Inst_SETS(InstDescriptor_SET):
  mnemonic = 'sets'
  opcode = DuckyOpcodes.SETS

class Inst_SETNS(InstDescriptor_SET):
  mnemonic = 'setns'
  opcode = DuckyOpcodes.SETNS

class Inst_SETG(InstDescriptor_SET):
  mnemonic = 'setg'
  opcode = DuckyOpcodes.SETG

class Inst_SETGE(InstDescriptor_SET):
  mnemonic = 'setge'
  opcode = DuckyOpcodes.SETGE

class Inst_SETL(InstDescriptor_SET):
  mnemonic = 'setl'
  opcode = DuckyOpcodes.SETL

class Inst_SETLE(InstDescriptor_SET):
  mnemonic = 'setle'
  opcode = DuckyOpcodes.SETLE

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

  @staticmethod
  def assemble_operands(logger, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    inst.r_addr = operands['register_n0']
    inst.r_test = operands['register_n1']
    inst.r_rep = operands['register_n2']

  @staticmethod
  def disassemble_operands(inst):
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
    core.registers.map[inst.reg].value = core.MEM_IN16(core.OFFSET_ADDR(inst))
    core.update_arith_flags(core.registers.map[inst.reg])

class Inst_LB(InstDescriptor_Generic_Binary_R_A):
  mnemonic = 'lb'
  opcode = DuckyOpcodes.LB

  @staticmethod
  def execute(core, inst):
    core.check_protected_reg(inst.reg)
    core.registers.map[inst.reg].value = core.MEM_IN8(core.OFFSET_ADDR(inst))
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
    core.MEM_OUT16(core.OFFSET_ADDR(inst), core.registers.map[inst.reg].value)

class Inst_STB(InstDescriptor_Generic_Binary_A_R):
  mnemonic    = 'stb'
  opcode = DuckyOpcodes.STB

  @staticmethod
  def execute(core, inst):
    core.MEM_OUT8(core.OFFSET_ADDR(inst), core.registers.map[inst.reg].value & 0xFF)

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
      r.value = x // y

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

    r.value = x // y

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

# Branching instructions
Inst_BE(DuckyInstructionSet)
Inst_BNE(DuckyInstructionSet)
Inst_BZ(DuckyInstructionSet)
Inst_BNZ(DuckyInstructionSet)
Inst_BO(DuckyInstructionSet)
Inst_BNO(DuckyInstructionSet)
Inst_BS(DuckyInstructionSet)
Inst_BNS(DuckyInstructionSet)
Inst_BG(DuckyInstructionSet)
Inst_BGE(DuckyInstructionSet)
Inst_BL(DuckyInstructionSet)
Inst_BLE(DuckyInstructionSet)

# SET* instructions
Inst_SETE(DuckyInstructionSet)
Inst_SETNE(DuckyInstructionSet)
Inst_SETZ(DuckyInstructionSet)
Inst_SETNZ(DuckyInstructionSet)
Inst_SETO(DuckyInstructionSet)
Inst_SETNO(DuckyInstructionSet)
Inst_SETS(DuckyInstructionSet)
Inst_SETNS(DuckyInstructionSet)
Inst_SETG(DuckyInstructionSet)
Inst_SETGE(DuckyInstructionSet)
Inst_SETL(DuckyInstructionSet)
Inst_SETLE(DuckyInstructionSet)

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
