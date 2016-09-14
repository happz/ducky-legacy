import ctypes
import enum
import re
import sys

from six import integer_types, string_types, add_metaclass
from six.moves import range
from functools import partial

from .registers import Registers, REGISTER_NAMES
from ..mm import u32_t, i32_t, UINT16_FMT, UINT32_FMT
from ..util import str2int
from ..errors import EncodingLargeValueError, UnalignedJumpTargetError, AssemblerError, InvalidOpcodeError, DivideByZeroError, InvalidInstructionSetError

PO_REGISTER  = r'(?P<register_n{operand_index}>(?:r\d\d?)|(?:sp)|(?:fp))'
PO_AREGISTER = r'(?P<address_register>r\d\d?|sp|fp)(?:\[(?:(?P<offset_sign>-|\+)?(?P<offset_immediate>0x[0-9a-fA-F]+|\d+))\])?'
PO_IMMEDIATE = r'(?:(?P<immediate>(?:-|\+)?(?:0x[0-9a-fA-F]+|\d+))|(?P<immediate_address>&?[a-zA-Z_\.][a-zA-Z0-9_\.]*))'

def UINT20_FMT(i):
  return '0x%05X' % (i & 0xFFFFF)

def encoding_to_u32(inst):
  return ctypes.cast(ctypes.byref(inst), ctypes.POINTER(u32_t)).contents.value

if hasattr(sys, 'pypy_version_info'):
  def u32_to_encoding(u, encoding):
    class _Cast(ctypes.Union):
      _pack_ = 0
      _fields_ = [
        ('overall',  u32_t),
        ('encoding', encoding)
      ]

    caster = _Cast()
    caster.overall = u32_t(u).value
    return caster.encoding

else:
  def u32_to_encoding(u, encoding):
    u = u32_t(u)
    e = encoding()

    ctypes.cast(ctypes.byref(e), ctypes.POINTER(encoding))[0] = ctypes.cast(ctypes.byref(u), ctypes.POINTER(encoding)).contents

    return e

def IE_OPCODE():
  return ('opcode', u32_t, 6)

def IE_FLAG(n):
  return (n, u32_t, 1)

def IE_REG(n):
  return (n, u32_t, 5)

def IE_IMM(n, l):
  return (n, u32_t, l)

class Encoding(ctypes.LittleEndianStructure):
  @staticmethod
  def sign_extend_immediate(logger, inst, sign_mask, ext_mask):
    logger.debug('sign_extend_immediate: inst=%s, sign_mask=%s, ext_mask=%s', inst, UINT32_FMT(sign_mask), UINT32_FMT(ext_mask))

    if __debug__:
      u = u32_t(ext_mask | inst.immediate) if inst.immediate & sign_mask else u32_t(inst.immediate)
      logger.debug('  result=%s', UINT32_FMT(u))

      return u.value

    else:
      i = inst.immediate
      return ((ext_mask | i) % 4294967296) if i & sign_mask else i
      return u32_t(ext_mask | inst.immediate).value if inst.immediate & sign_mask else u32_t(inst.immediate).value

class EncodingR(ctypes.LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    IE_OPCODE(),                # 0
    IE_REG('reg1'),             # 6
    IE_REG('reg2'),             # 11
    IE_FLAG('immediate_flag'),  # 16
    IE_IMM('immediate', 15),    # 17
  ]

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 17
    slot.patch_size = 15

  @staticmethod
  def sign_extend_immediate(logger, inst):
    return Encoding.sign_extend_immediate(logger, inst, 0x4000, 0xFFFF8000)

  def __repr__(self):
    return '<EncodingR: opcode=%s, reg1=%s, reg2=%s, immediate_flag=%s, immediate=%s>' % (self.opcode, self.reg1, self.reg2, self.immediate_flag, UINT16_FMT(self.immediate))

class EncodingC(ctypes.LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    IE_OPCODE(),                # 0
    IE_REG('reg'),              # 6
    IE_IMM('flag', 3),          # 11
    IE_FLAG('value'),           # 14
    IE_FLAG('immediate_flag'),  # 25
    IE_IMM('immediate', 16)     # 16
  ]

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 16
    slot.patch_size = 16

  @staticmethod
  def sign_extend_immediate(logger, inst):
    return Encoding.sign_extend_immediate(logger, inst, 0x8000, 0xFFFF0000)

  def __repr__(self):
    return '<EncodingC: opcode=%s, reg=%s, flag=%s, value=%s, immediate_flag=%s, immediate=0x%04X>' % (self.opcode, self.reg, self.flag, self.value, self.immediate_flag, self.immediate)

class EncodingS(ctypes.LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    IE_OPCODE(),                # 0
    IE_REG('reg1'),             # 6
    IE_REG('reg2'),             # 11
    IE_IMM('flag', 3),          # 16
    IE_FLAG('value'),           # 19
    IE_FLAG('immediate_flag'),  # 20
    IE_IMM('immediate', 11)     # 21
  ]

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 21
    slot.patch_size = 11

  @staticmethod
  def sign_extend_immediate(logger, inst):
    return Encoding.sign_extend_immediate(logger, inst, 0x400, 0xFFFFF800)

  def __repr__(self):
    return '<EncodingS: opcode=%s, reg1=%s, reg2=%s, flag=%s, value=%s, immediate_flag=%s, immediate=0x%03X>' % (self.opcode, self.reg1, self.reg2, self.flag, self.value, self.immediate_flag, self.immediate)

class EncodingI(ctypes.LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    IE_OPCODE(),                # 0
    IE_REG('reg'),              # 6
    IE_FLAG('immediate_flag'),  # 11
    IE_IMM('immediate', 20),    # 12
  ]

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    logger.debug('fill_reloc_slot: inst=%s, slot=%s', inst, slot)

    slot.patch_offset = 12
    slot.patch_size = 20

  @staticmethod
  def sign_extend_immediate(logger, inst):
    return Encoding.sign_extend_immediate(logger, inst, 0x80000, 0xFFF00000)

  def __repr__(self):
    return '<EncodingI: opcode=%s, reg=%s, immediate_flag=%s, immediate=%s>' % (self.opcode, self.reg, self.immediate_flag, UINT20_FMT(self.immediate))

class EncodingA(ctypes.LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    IE_OPCODE(),                # 0
    IE_REG('reg1'),             # 6
    IE_REG('reg2'),             # 11
    IE_REG('reg3')              # 16
  ]

  def __repr__(self):
    return '<EncodingA: opcode=%s, reg1=%s, reg2=%s, reg3=%s>' % (self.opcode, self.reg1, self.reg2, self.reg3)

def ENCODE(logger, buffer, inst, field, size, value, raise_on_large_value = False):
  logger.debug('ENCODE: inst=%s, field=%s, size=%s, value=%s, raise_on_large_value=%s', inst, field, size, value, raise_on_large_value)

  setattr(inst, field, value)

  logger.debug('ENCODE: inst=%s', inst)

  if value >= 2 ** size:
    e = buffer.get_error(EncodingLargeValueError, 'inst=%s, field=%s, size=%s, value=%s' % (inst, field, size, UINT32_FMT(value)))

    if raise_on_large_value is True:
      raise e

    e.log(logger.warn)

class Descriptor(object):
  mnemonic      = None
  opcode        = None
  operands      = None

  # this is a default encoding, and by the way it silents Codacy's warning
  encoding      = EncodingR

  pattern       = None

  relative_address = False
  inst_aligned = False

  def __init__(self, instruction_set):
    super(Descriptor, self).__init__()

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

      pattern += r' ' + r',\s*'.join(operand_patterns)

    pattern = r'^' + pattern + '(?:\s*[;#].*)?$'
    self.pattern = re.compile(pattern, re.MULTILINE)

    self.instruction_set.instructions.append(self)

  @staticmethod
  def jit(core, inst):
    return None

  @staticmethod
  def execute(core, inst):
    raise NotImplementedError('%s does not implement execute method' % inst.opcode)

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    pass

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    inst.fill_reloc_slot(logger, inst, slot)

  @staticmethod
  def disassemble_operands(logger, inst):
    return []

  @classmethod
  def disassemble_mnemonic(cls, inst):
    return cls.mnemonic

  def emit_instruction(self, logger, buffer, line):
    DEBUG = logger.debug

    DEBUG('emit_instruction: input line: %s', line)

    binst = self.encoding()

    DEBUG('emit_instruction: encoding=%s', self.encoding.__name__)
    DEBUG('emit_instruction: desc is %s', self)

    binst.opcode = self.opcode

    raw_match = self.pattern.match(line)
    matches = raw_match.groupdict()
    DEBUG('emit_instruction: matches=%s', matches)

    operands = {}

    def str2reg(r):
      if r == 'sp':
        return Registers.SP

      if r == 'fp':
        return Registers.FP

      return Registers(int(r[1:]))

    if self.operands and len(self.operands):
      for operand_index in range(0, len(self.operands)):
        reg_group_name = 'register_n{}'.format(operand_index)

        if reg_group_name in matches and matches[reg_group_name]:
          operands[reg_group_name] = str2reg(matches[reg_group_name])
          continue

        if 'address_register' in matches and matches['address_register']:
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
            k = -1 if 'offset_sign' in matches and matches['offset_sign'] and matches['offset_sign'].strip() == '-' else 1
            operands['offset_immediate'] = k * str2int(matches['offset_immediate'])

          continue

        imm = matches.get('immediate')
        if imm is not None:
          operands['immediate'] = str2int(imm)
          continue

        imm = matches.get('immediate_address')
        if imm is not None:
          if imm[0] != '&':
            imm = '&' + imm

          operands['immediate'] = imm
          continue

        raise Exception('Unhandled operand: {}'.format(matches))

    else:
      pass

    try:
      self.assemble_operands(logger, buffer, binst, operands)

    except AssemblerError as e:
      e.location = buffer.location.copy()
      raise e

    return binst

class Descriptor_R(Descriptor):
  operands = 'r'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])

  @staticmethod
  def disassemble_operands(logger, inst):
    return [REGISTER_NAMES[inst.reg1]]

class Descriptor_I(Descriptor):
  operands = 'i'

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    v = operands['immediate']

    if isinstance(v, integer_types):
      inst.immediate = v

    elif isinstance(v, string_types):
      inst.refers_to = Reference(label = v)

  @staticmethod
  def disassemble_operands(logger, inst):
    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT16_FMT(inst.immediate)]

class Descriptor_RI(Descriptor):
  operands = 'ri'
  encoding = EncodingI

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    if 'register_n0' in operands:
      ENCODE(logger, buffer, inst, 'reg', 5, operands['register_n0'])

    else:
      v = operands['immediate']

      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

      if isinstance(v, integer_types):
        ENCODE(logger, buffer, inst, 'immediate', 20, v)

      elif isinstance(v, string_types):
        inst.refers_to = Reference(label = v)

  @staticmethod
  def disassemble_operands(logger, inst):
    if inst.immediate_flag == 0:
      return [REGISTER_NAMES[inst.reg]]

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT32_FMT(inst.immediate)]

class Descriptor_R_I(Descriptor):
  operands = 'r,i'
  encoding = EncodingI

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg', 5, operands['register_n0'])
    ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

    v = operands['immediate']

    if isinstance(v, integer_types):
      ENCODE(logger, buffer, inst, 'immediate', 20, v)

    elif isinstance(v, string_types):
      inst.refers_to = Reference(label = v)

  @staticmethod
  def disassemble_operands(logger, inst):
    return [REGISTER_NAMES[inst.reg], str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT20_FMT(inst.immediate)]

class Descriptor_R_RI(Descriptor):
  operands = 'r,ri'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])

    if 'register_n1' in operands:
      ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])

    else:
      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

      v = operands['immediate']

      if isinstance(v, integer_types):
        ENCODE(logger, buffer, inst, 'immediate', 15, v)

      elif isinstance(v, string_types):
        inst.refers_to = Reference(label = v)

  @staticmethod
  def disassemble_operands(logger, inst):
    if inst.immediate_flag == 0:
      return [REGISTER_NAMES[inst.reg1], REGISTER_NAMES[inst.reg2]]

    return [REGISTER_NAMES[inst.reg1], str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT16_FMT(inst.immediate)]

class Descriptor_R_R(Descriptor):
  operands = 'r,r'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])
    ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])

  @staticmethod
  def disassemble_operands(logger, inst):
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
    cls.opcode_encoding_map = {}

    for desc in cls.instructions:
      cls.opcode_desc_map[desc.opcode] = desc
      cls.opcode_encoding_map[desc.opcode] = desc.encoding

  @classmethod
  def decode_instruction(cls, logger, inst, core = None):
    logger.debug('%s.decode_instruction: inst=%s, core=%s', cls.__name__, inst, core)

    opcode = inst & 0x3F

    if opcode not in cls.opcode_desc_map:
      raise InvalidOpcodeError(opcode, core = core)

    return u32_to_encoding(inst, cls.opcode_encoding_map[opcode]), cls.opcode_desc_map[opcode], opcode

  @classmethod
  def disassemble_instruction(cls, logger, inst):
    logger.debug('%s.disassemble_instruction: inst=%s (%s)', cls.__name__, inst, inst.__class__.__name__)

    if isinstance(inst, ctypes.LittleEndianStructure):
      inst, desc = inst, cls.opcode_desc_map[inst.opcode]

    else:
      inst, desc, _ = cls.decode_instruction(logger, inst)

    mnemonic = desc.disassemble_mnemonic(inst)
    operands = desc.disassemble_operands(logger, inst)

    return (mnemonic + ' ' + ', '.join(operands)) if operands else mnemonic

#
# Main instruction set
#

def RI_VAL(core, inst, reg, sign_extend = True):
  if inst.immediate_flag == 1:
    if sign_extend is True:
      return inst.sign_extend_immediate(core.LOGGER, inst)

    return inst.immediate % 4294967296

  return core.registers[getattr(inst, reg)]

def RI_ADDR(core, inst, reg):
  core.DEBUG('RI_ADDR: inst=%s, reg=%s', inst, reg)

  base = core.registers[reg]
  offset = inst.sign_extend_immediate(core.LOGGER, inst) if inst.immediate_flag == 1 else 0

  return (base + offset) % 4294967296

def JUMP(core, inst, reg):
  core.DEBUG('JUMP: inst=%s', inst)
  core.DEBUG('  IP=%s', UINT32_FMT(core.registers.ip))

  if inst.immediate_flag == 0:
    reg = getattr(inst, reg)
    core.DEBUG('  register=%d, value=%s', reg, UINT32_FMT(core.registers[reg]))
    core.registers.ip = core.registers[reg]

  else:
    v = inst.sign_extend_immediate(core.LOGGER, inst)
    nip = (core.registers.ip + (v << 2)) % 4294967296
    core.DEBUG('  offset=%s, aligned=%s, ip=%s, new=%s', UINT32_FMT(v), UINT32_FMT(v << 2), UINT32_FMT(core.registers.ip), UINT32_FMT(nip))
    core.registers.ip = nip

  core.DEBUG('JUMP: new ip=%s', UINT32_FMT(core.registers.ip))

def update_arith_flags(core, reg):
  """
  Set relevant arithmetic flags according to content of registers. Flags are set to zero at the beginning,
  then content of each register is examined, and ``S`` and ``Z`` flags are set.

  ``E`` flag is not touched, ``O`` flag is set to zero.

  :param u32_t reg: register
  """

  core.arith_zero = False
  core.arith_overflow = False
  core.arith_sign = False

  if reg == 0:
    core.arith_zero = True

  if reg & 0x80000000 != 0:
    core.arith_sign = True

class DuckyOpcodes(enum.IntEnum):
  NOP    =  0

  # Memory load/store
  LW     =  1
  LS     =  2
  LB     =  3
  STW    =  4
  STS    =  5
  STB    =  6
  CAS    =  7
  LA     =  8

  LI     =  9
  LIU    = 10
  MOV    = 11
  SWP    = 12

  INT    = 13
  RETINT = 14

  CALL   = 15
  RET    = 16

  CLI    = 17
  STI    = 18
  RST    = 19
  HLT    = 20
  IDLE   = 21
  LPM    = 22
  IPI    = 23

  PUSH   = 24
  POP    = 25

  INC    = 26
  DEC    = 27
  ADD    = 28
  SUB    = 29
  MUL    = 30
  DIV    = 31
  UDIV   = 32
  MOD    = 33

  AND    = 34
  OR     = 35
  XOR    = 36
  NOT    = 37
  SHL    = 38
  SHR    = 39
  SHRS   = 40

  # Branch instructions
  J      = 46

  # Condition instructions
  CMP    = 47
  CMPU   = 48
  SET    = 49
  BRANCH = 50
  SELECT = 51

  # Control instructions
  CTR    = 60
  CTW    = 61
  FPTC   = 62
  SIS    = 63


class NOP(Descriptor):
  mnemonic = 'nop'
  opcode = DuckyOpcodes.NOP
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    pass


#
# Interrupts
#
class INT(Descriptor_RI):
  mnemonic      = 'int'
  opcode        = DuckyOpcodes.INT

  @staticmethod
  def execute(core, inst):
    core._enter_exception(RI_VAL(core, inst, 'reg'))

class IPI(Descriptor_R_RI):
  mnemonic = 'ipi'
  opcode = DuckyOpcodes.IPI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()

    cpuid = core.registers[inst.reg1]
    cpuid, coreid = cpuid >> 16, cpuid & 0xFFFF

    core.cpu.machine.cpus[cpuid].cores[coreid].irq(RI_VAL(core, inst, 'reg2'))

class RETINT(Descriptor):
  mnemonic = 'retint'
  opcode   = DuckyOpcodes.RETINT
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core._exit_exception()

#
# Jumps
#
class _JUMP(Descriptor):
  operands = 'ri'
  encoding = EncodingI
  relative_address = True
  inst_aligned = True

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    if 'register_n0' in operands:
      ENCODE(logger, buffer, inst, 'reg', 5, operands['register_n0'])

    else:
      v = operands['immediate']

      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

      if isinstance(v, integer_types):
        if v & 0x3 != 0:
          raise buffer.get_error(UnalignedJumpTargetError, 'address=%s' % UINT32_FMT(v))

        ENCODE(logger, buffer, inst, 'immediate', 20, v >> 2)

      elif isinstance(v, string_types):
        inst.refers_to = Reference(label = v)

  @staticmethod
  def disassemble_operands(logger, inst):
    if inst.immediate_flag == 0:
      return [REGISTER_NAMES[inst.reg]]

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT32_FMT(inst.immediate << 2)]

class CALL(_JUMP):
  mnemonic      = 'call'
  opcode        = DuckyOpcodes.CALL

  @staticmethod
  def execute(core, inst):
    core.create_frame()

    JUMP(core, inst, 'reg')

    if core.check_frames:
      core.frames[-1].IP = core.registers.ip

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    push = core._raw_push

    if inst.immediate_flag == 0:
      reg = inst.reg

      def __jit_call():
        push(regset.ip)
        push(regset.fp)
        regset.fp = regset.sp
        regset.ip = regset[reg]

      return __jit_call

    else:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

      def __jit_call():
        push(regset.ip)
        push(regset.fp)
        regset.fp = regset.sp
        regset.ip = (regset.ip + i) % 4294967296

      return __jit_call

class J(_JUMP):
  mnemonic = 'j'
  opcode   = DuckyOpcodes.J

  @staticmethod
  def execute(core, inst):
    JUMP(core, inst, 'reg')

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 0:
      reg = inst.reg

      def __jit_j():
        regset.ip = regset[reg]

      return __jit_j

    else:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

      def __jit_j():
        regset.ip = (regset.ip + i) % 4294967296

      return __jit_j

class RET(Descriptor):
  mnemonic = 'ret'
  opcode   = DuckyOpcodes.RET
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.destroy_frame()

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    pop = core._raw_pop

    def __jit_ret():
      regset.fp = pop()
      regset.ip = pop()

    return __jit_ret

#
# CPU
#
class LPM(Descriptor):
  mnemonic = 'lpm'
  opcode = DuckyOpcodes.LPM
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.privileged = False

class CLI(Descriptor):
  mnemonic = 'cli'
  opcode = DuckyOpcodes.CLI
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.hwint_allowed = False

class STI(Descriptor):
  mnemonic = 'sti'
  opcode = DuckyOpcodes.STI
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.hwint_allowed = True

class HLT(Descriptor_RI):
  mnemonic = 'hlt'
  opcode = DuckyOpcodes.HLT

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.exit_code = RI_VAL(core, inst, 'reg')
    core.halt()

class RST(Descriptor):
  mnemonic = 'rst'
  opcode = DuckyOpcodes.RST
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.reset()

class IDLE(Descriptor):
  mnemonic = 'idle'
  opcode = DuckyOpcodes.IDLE
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.change_runnable_state(idle = True)

class SIS(Descriptor_RI):
  mnemonic = 'sis'
  opcode = DuckyOpcodes.SIS

  @staticmethod
  def execute(core, inst):
    core.instruction_set = get_instruction_set(RI_VAL(core, inst, 'reg'))


#
# Stack
#
class PUSH(Descriptor_RI):
  mnemonic = 'push'
  opcode = DuckyOpcodes.PUSH

  @staticmethod
  def execute(core, inst):
    core._raw_push(RI_VAL(core, inst, 'reg'))

  @staticmethod
  def jit(core, inst):
    push = core._raw_push
    regset = core.registers

    if inst.immediate_flag == 0:
      reg = inst.reg

      def __jit_push():
        push(regset[reg])

      return __jit_push

    else:
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_push():
        push(i)

      return __jit_push

class POP(Descriptor_R):
  mnemonic = 'pop'
  opcode = DuckyOpcodes.POP

  @staticmethod
  def execute(core, inst):
    core.pop(inst.reg1)
    update_arith_flags(core, core.registers[inst.reg1])

  @staticmethod
  def jit(core, inst):
    pop = core._raw_pop
    regset = core.registers
    reg = inst.reg1

    def __jit_pop():
      regset[reg] = v = pop()
      core.arith_zero = v == 0
      core.arith_overflow = False
      core.arith_sign = (v & 0x80000000) != 0

    return __jit_pop

#
# Arithmetic
#
class INC(Descriptor_R):
  mnemonic = 'inc'
  opcode = DuckyOpcodes.INC

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = (core.registers[inst.reg1] + 1) % 4294967296
    update_arith_flags(core, core.registers[inst.reg1])
    core.arith_overflow = core.registers[inst.reg1] == 0

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    reg = inst.reg1

    def __jit_inc():
      old, new = regset[reg], (regset[reg] + 1) % 4294967296
      regset[reg] = new

      if old == 0:
        core.arith_zero = core.arith_overflow = core.arith_sign = False

      elif old == 0xFFFFFFFF:
        core.arith_zero = core.arith_overflow = True
        core.arith_sign = False

      else:
        core.arith_zero = False
        core.arith_overflow = False
        core.arith_sign = (new & 0x80000000) != 0

    return __jit_inc

class DEC(Descriptor_R):
  mnemonic = 'dec'
  opcode = DuckyOpcodes.DEC

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = (core.registers[inst.reg1] - 1) % 4294967296
    update_arith_flags(core, core.registers[inst.reg1])

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    reg = inst.reg1

    def __jit_dec():
      old, new = regset[reg], (regset[reg] - 1) % 4294967296
      regset[reg] = new

      if old == 0:
        core.arith_zero = core.arith_overflow = False
        core.arith_sign = True

      elif old == 1:
        core.arith_zero = True
        core.arith_overflow = core.arith_sign = False

      else:
        core.arith_zero = core.arith_overflow = False
        core.arith_sign = (new & 0x80000000) != 0

    return __jit_dec

class _BINOP(Descriptor_R_RI):
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    regset = core.registers
    r = regset[inst.reg1]
    v = RI_VAL(core, inst, 'reg2')

    if inst.opcode == DuckyOpcodes.ADD:
      v = (r + v)

    elif inst.opcode == DuckyOpcodes.SUB:
      v = (r - v)

    elif inst.opcode == DuckyOpcodes.MUL:
      x = i32_t(r).value
      y = i32_t(v).value
      v = x * y

    elif inst.opcode == DuckyOpcodes.DIV:
      y = i32_t(v).value
      if y == 0:
        raise DivideByZeroError(core = core)

      x = i32_t(r).value

      if abs(y) > abs(x):
        v = 0

      else:
        v = x // y

    elif inst.opcode == DuckyOpcodes.UDIV:
      y = u32_t(v).value
      if y == 0:
        raise DivideByZeroError(core = core)

      x = u32_t(r).value
      v = x // y

    elif inst.opcode == DuckyOpcodes.MOD:
      y = i32_t(v).value
      if y == 0:
        raise DivideByZeroError(core = core)

      x = i32_t(r).value
      v = x % y

    regset[inst.reg1] = v % 4294967296
    update_arith_flags(core, regset[inst.reg1])

    if v > 0xFFFFFFFF:
      core.arith_overflow = True

class ADD(_BINOP):
  mnemonic = 'add'
  opcode = DuckyOpcodes.ADD

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_add():
        v = regset[reg] + i
        regset[reg] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_add

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_add():
        v = regset[reg1] + regset[reg2]
        regset[reg1] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_add

class SUB(_BINOP):
  mnemonic = 'sub'
  opcode = DuckyOpcodes.SUB

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_sub():
        v = regset[reg] - i
        regset[reg] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_sub

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_sub():
        v = regset[reg1] - regset[reg2]
        regset[reg1] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_sub

class MUL(_BINOP):
  mnemonic = 'mul'
  opcode = DuckyOpcodes.MUL

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = i32_t(inst.sign_extend_immediate(core.LOGGER, inst)).value

      def __jit_mul():
        v = i32_t(regset[reg]).value * i
        regset[reg] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_mul

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_mul():
        v = i32_t(regset[reg1]).value * i32_t(regset[reg2]).value
        regset[reg1] = r = v % 4294967296
        core.arith_zero = r == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_mul

class DIV(_BINOP):
  mnemonic = 'div'
  opcode = DuckyOpcodes.DIV

class UDIV(_BINOP):
  mnemonic = 'udiv'
  opcode = DuckyOpcodes.UDIV

class MOD(_BINOP):
  mnemonic = 'mod'
  opcode = DuckyOpcodes.MOD


#
# Conditional and unconditional jumps
#
class _COND(Descriptor):
  FLAGS = ['arith_equal', 'arith_zero', 'arith_overflow', 'arith_sign', 'l', 'g']
  GFLAGS = [0, 1, 2, 3]
  MNEMONICS = ['e', 'z', 'o', 's', 'g', 'l']

  @staticmethod
  def set_condition(logger, buffer, inst, flag, value):
    logger.debug('set_condition: flag=%s, value=%s', flag, value)

    ENCODE(logger, buffer, inst, 'flag', 3, _COND.FLAGS.index(flag))
    ENCODE(logger, buffer, inst, 'value', 1, 1 if value is True else 0)

  @staticmethod
  def evaluate(core, inst):
    # genuine flags
    if inst.flag in _COND.GFLAGS and inst.value == getattr(core, _COND.FLAGS[inst.flag]):
      return True

    # "less than" flag
    if inst.flag == 4:
      if inst.value == 1 and core.arith_sign is True and core.arith_equal is not True:
        return True

      if inst.value == 0 and (core.arith_sign is not True or core.arith_equal is True):
        return True

    # "greater than" flag
    if inst.flag == 5:
      if inst.value == 1 and core.arith_sign is not True and core.arith_equal is not True:
        return True

      if inst.value == 0 and (core.arith_sign is True or core.arith_equal is True):
        return True

    return False

class _BRANCH(_COND):
  encoding = EncodingC
  operands = 'ri'
  opcode = DuckyOpcodes.BRANCH
  relative_address = True
  inst_aligned = True

  @classmethod
  def assemble_operands(cls, logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    if 'register_n0' in operands:
      ENCODE(logger, buffer, inst, 'reg', 5, operands['register_n0'])

    else:
      v = operands['immediate']

      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

      if isinstance(v, integer_types):
        if v & 0x3 != 0:
          raise buffer.get_error(UnalignedJumpTargetError, 'address=%s' % UINT32_FMT(v))

        ENCODE(logger, buffer, inst, 'immediate', 16, v >> 2)

      elif isinstance(v, string_types):
        inst.refers_to = Reference(label = v)

    set_condition = partial(_COND.set_condition, logger, buffer, inst)

    if cls is BE:
      set_condition('arith_equal', True)

    elif cls is BNE:
      set_condition('arith_equal', False)

    elif cls is BZ:
      set_condition('arith_zero', True)

    elif cls is BNZ:
      set_condition('arith_zero', False)

    elif cls is BO:
      set_condition('arith_overflow', True)

    elif cls is BNO:
      set_condition('arith_overflow', False)

    elif cls is BS:
      set_condition('arith_sign', True)

    elif cls is BNS:
      set_condition('arith_sign', False)

    elif cls is BL:
      set_condition('l', True)

    elif cls is BLE:
      set_condition('g', False)

    elif cls is BG:
      set_condition('g', True)

    elif cls is BGE:
      set_condition('l', False)

  @staticmethod
  def fill_reloc_slot(logger, inst, slot):
    inst.fill_reloc_slot(logger, inst, slot)

    slot.flags.inst_aligned = True

  @staticmethod
  def disassemble_operands(logger, inst):
    if inst.immediate_flag == 0:
      return [REGISTER_NAMES[inst.reg]]

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT32_FMT(inst.immediate << 2)]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in _COND.GFLAGS:
      return 'b%s%s' % ('n' if inst.value == 0 else '', _COND.MNEMONICS[inst.flag])

    else:
      if inst.flag == _COND.FLAGS.index('l'):
        return 'bl' if inst.value == 1 else 'bge'

      elif inst.flag == _COND.FLAGS.index('g'):
        return 'bg' if inst.value == 1 else 'ble'

  @staticmethod
  def execute(core, inst):
    if _COND.evaluate(core, inst):
      JUMP(core, inst, 'reg')

  @staticmethod
  def jit(core, inst):
    core.DEBUG('JIT: %s', inst)

    regset = core.registers

    if inst.immediate_flag == 1:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

    else:
      reg = inst.reg

    if inst.flag in _COND.GFLAGS:
      if inst.flag == 0:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_ne():
              if core.arith_equal is False:
                regset.ip = regset[reg]

            return __branch_ne

          else:
            def __branch_ne():
              if core.arith_equal is False:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_ne

        else:
          if inst.immediate_flag == 0:
            def __branch_e():
              if core.arith_equal is True:
                regset.ip = regset[reg]

            return __branch_e

          else:
            def __branch_e():
              if core.arith_equal is True:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_e

      elif inst.flag == 1:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_nz():
              if core.arith_zero is False:
                regset.ip = regset[reg]

            return __branch_nz

          else:
            def __branch_nz():
              if core.arith_zero is False:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_nz

        else:
          if inst.immediate_flag == 0:
            def __branch_z():
              if core.arith_zero is True:
                regset.ip = regset[reg]

            return __branch_z

          else:
            def __branch_z():
              if core.arith_zero is True:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_z

      elif inst.flag == 2:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_no():
              if core.arith_overflow is False:
                regset.ip = regset[reg]

            return __branch_no

          else:
            def __branch_no():
              if core.arith_overflow is False:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_no

        else:
          if inst.immediate_flag == 0:
            def __branch_o():
              if core.arith_overflow is True:
                regset.ip = regset[reg]

            return __branch_o

          else:
            def __branch_o():
              if core.arith_overflow is True:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_o

      elif inst.flag == 3:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_ns():
              if core.arith_sign is False:
                regset.ip = regset[reg]

            return __branch_ns

          else:
            def __branch_ns():
              if core.arith_sign is False:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_ns

        else:
          if inst.immediate_flag == 0:
            def __branch_s():
              if core.arith_sign is True:
                regset.ip = regset[reg]

            return __branch_s

          else:
            def __branch_s():
              if core.arith_sign is True:
                regset.ip = (regset.ip + i) % 4294967296

            return __branch_s

    return None

class _SET(_COND):
  encoding = EncodingS
  operands = 'r'
  opcode = DuckyOpcodes.SET

  @classmethod
  def assemble_operands(cls, logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])

    set_condition = partial(_COND.set_condition, logger, buffer, inst)

    if cls is SETE:
      set_condition('arith_equal', True)

    elif cls is SETNE:
      set_condition('arith_equal', False)

    elif cls is SETZ:
      set_condition('arith_zero', True)

    elif cls is SETNZ:
      set_condition('arith_zero', False)

    elif cls is SETO:
      set_condition('arith_overflow', True)

    elif cls is SETNO:
      set_condition('arith_overflow', False)

    elif cls is SETS:
      set_condition('arith_sign', True)

    elif cls is SETNS:
      set_condition('arith_sign', False)

    elif cls is SETL:
      set_condition('l', True)

    elif cls is SETLE:
      set_condition('g', False)

    elif cls is SETG:
      set_condition('g', True)

    elif cls is SETGE:
      set_condition('l', False)

  @staticmethod
  def disassemble_operands(logger, inst):
    return [REGISTER_NAMES[inst.reg1]]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in _COND.GFLAGS:
      return 'set%s%s' % ('n' if inst.value == 0 else '', _COND.MNEMONICS[inst.flag])

    else:
      return 'set%s%s' % (_COND.MNEMONICS[inst.flag], 'e' if inst.value == 1 else '')

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = 1 if _COND.evaluate(core, inst) is True else 0
    update_arith_flags(core, core.registers[inst.reg1])

class _SELECT(Descriptor):
  encoding = EncodingS
  operands = 'r,ri'
  opcode = DuckyOpcodes.SELECT

  @classmethod
  def assemble_operands(cls, logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])

    if 'register_n1' in operands:
      ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])

    else:
      v = operands['immediate']

      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)

      if isinstance(v, integer_types):
        ENCODE(logger, buffer, inst, 'immediate', 11, v)

      elif isinstance(v, string_types):
        from .assemble import Reference
        inst.refers_to = Reference(label = v)

    set_condition = partial(_COND.set_condition, logger, buffer, inst)

    if cls is SELE:
      set_condition('arith_equal', True)

    elif cls is SELNE:
      set_condition('arith_equal', False)

    elif cls is SELZ:
      set_condition('arith_zero', True)

    elif cls is SELNZ:
      set_condition('arith_zero', False)

    elif cls is SELO:
      set_condition('arith_overflow', True)

    elif cls is SELNO:
      set_condition('arith_overflow', False)

    elif cls is SELS:
      set_condition('arith_sign', True)

    elif cls is SELNS:
      set_condition('arith_sign', False)

    elif cls is SELL:
      set_condition('l', True)

    elif cls is SELLE:
      set_condition('g', False)

    elif cls is SELG:
      set_condition('g', True)

    elif cls is SELGE:
      set_condition('l', False)

  @staticmethod
  def disassemble_operands(logger, inst):
    if inst.immediate_flag == 0:
      return [REGISTER_NAMES[inst.reg1], REGISTER_NAMES[inst.reg2]]

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT32_FMT(inst.immediate)]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in _COND.GFLAGS:
      return 'sel%s%s' % ('n' if inst.value == 0 else '', _COND.MNEMONICS[inst.flag])

    else:
      return 'sel%s%s' % (_COND.MNEMONICS[inst.flag], 'e' if inst.value == 1 else '')

  @staticmethod
  def execute(core, inst):
    if _COND.evaluate(core, inst) is False:
      core.registers[inst.reg1] = RI_VAL(core, inst, 'reg2')

    update_arith_flags(core, core.registers[inst.reg1])

class _CMP(Descriptor_R_RI):
  encoding = EncodingR

  @staticmethod
  def evaluate(core, x, y, signed = True):
    """
    Compare two numbers, and update relevant flags. Signed comparison is used unless ``signed`` is ``False``.
    All arithmetic flags are set to zero before the relevant ones are set.

    ``O`` flag is reset like the others, therefore caller has to take care of it's setting if it's required
    to set it.

    :param u32 x: left hand number
    :param u32 y: right hand number
    :param bool signed: use signed, defaults to ``True``
    """

    core.arith_equal = False
    core.arith_zero = False
    core.arith_overflow = False
    core.arith_sign = False

    if x == y:
      core.arith_equal = True

      if x == 0:
        core.arith_zero = True

      return

    if signed:
      x = i32_t(x).value
      y = i32_t(y).value

    if x < y:
      core.arith_sign = True

class CMP(_CMP):
  mnemonic = 'cmp'
  opcode = DuckyOpcodes.CMP

  @staticmethod
  def execute(core, inst):
    _CMP.evaluate(core, core.registers[inst.reg1], RI_VAL(core, inst, 'reg2'))

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 0:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_cmp():
        x = regset[reg1]
        y = regset[reg2]

        core.arith_overflow = False

        if x == y:
          core.arith_equal = True
          core.arith_zero = x == 0
          core.arith_sign = False
          return

        core.arith_equal = False
        core.arith_zero  = False
        core.arith_sign = i32_t(x).value < i32_t(y).value

      return __jit_cmp

    else:
      reg = inst.reg1
      y = inst.sign_extend_immediate(core.LOGGER, inst)
      y_signed = i32_t(y).value

      def __jit_cmp():
        x = regset[reg]

        core.arith_overflow = False

        if x == y:
          core.arith_equal = True
          core.arith_zero = x == 0
          core.arith_sign = False
          return

        core.arith_equal = False
        core.arith_zero  = False
        core.arith_sign = i32_t(x).value < y_signed

      return __jit_cmp

    return None

class CMPU(_CMP):
  mnemonic = 'cmpu'
  opcode = DuckyOpcodes.CMPU

  @staticmethod
  def execute(core, inst):
    _CMP.evaluate(core, core.registers[inst.reg1], RI_VAL(core, inst, 'reg2', sign_extend = False), signed = False)

class BE(_BRANCH):
  mnemonic = 'be'

class BNE(_BRANCH):
  mnemonic = 'bne'

class BNS(_BRANCH):
  mnemonic = 'bns'

class BNZ(_BRANCH):
  mnemonic = 'bnz'

class BS(_BRANCH):
  mnemonic = 'bs'

class BZ(_BRANCH):
  mnemonic = 'bz'

class BO(_BRANCH):
  mnemonic = 'bo'

class BNO(_BRANCH):
  mnemonic = 'bno'

class BG(_BRANCH):
  mnemonic = 'bg'

class BGE(_BRANCH):
  mnemonic = 'bge'

class BL(_BRANCH):
  mnemonic = 'bl'

class BLE(_BRANCH):
  mnemonic = 'ble'

class SETE(_SET):
  mnemonic = 'sete'

class SETNE(_SET):
  mnemonic = 'setne'

class SETZ(_SET):
  mnemonic = 'setz'

class SETNZ(_SET):
  mnemonic = 'setnz'

class SETO(_SET):
  mnemonic = 'seto'

class SETNO(_SET):
  mnemonic = 'setno'

class SETS(_SET):
  mnemonic = 'sets'

class SETNS(_SET):
  mnemonic = 'setns'

class SETG(_SET):
  mnemonic = 'setg'

class SETGE(_SET):
  mnemonic = 'setge'

class SETL(_SET):
  mnemonic = 'setl'

class SETLE(_SET):
  mnemonic = 'setle'

class SELE(_SELECT):
  mnemonic = 'sele'

class SELNE(_SELECT):
  mnemonic = 'selne'

class SELZ(_SELECT):
  mnemonic = 'selz'

class SELNZ(_SELECT):
  mnemonic = 'selnz'

class SELO(_SELECT):
  mnemonic = 'selo'

class SELNO(_SELECT):
  mnemonic = 'selno'

class SELS(_SELECT):
  mnemonic = 'sels'

class SELNS(_SELECT):
  mnemonic = 'selns'

class SELG(_SELECT):
  mnemonic = 'selg'

class SELGE(_SELECT):
  mnemonic = 'selge'

class SELL(_SELECT):
  mnemonic = 'sell'

class SELLE(_SELECT):
  mnemonic = 'selle'

#
# Bit operations
#
class _BITOP(Descriptor_R_RI):
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    r = core.registers[inst.reg1]
    v = RI_VAL(core, inst, 'reg2')

    if inst.opcode == DuckyOpcodes.AND:
      value = r & v

    elif inst.opcode == DuckyOpcodes.OR:
      value = r | v

    elif inst.opcode == DuckyOpcodes.XOR:
      value = r ^ v

    elif inst.opcode == DuckyOpcodes.SHL:
      value = r << min(v, 32)

    elif inst.opcode == DuckyOpcodes.SHR:
      value = r >> min(v, 32)

    elif inst.opcode == DuckyOpcodes.SHRS:
      shift = min(v, 32)
      if r & 0x80000000 == 0:
        value = r >> shift
      else:
        value = (r >> shift) | (((1 << shift) - 1) << (32 - shift))

    core.registers[inst.reg1] = (value % 4294967296)
    update_arith_flags(core, core.registers[inst.reg1])

    if value > 0xFFFFFFFF:
      core.arith_overflow = True

class AND(_BITOP):
  mnemonic = 'and'
  opcode = DuckyOpcodes.AND

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_and():
        regset[reg] = v = regset[reg] & i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_and

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_and():
        regset[reg1] = v = regset[reg1] & regset[reg2]
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_and

class OR(_BITOP):
  mnemonic = 'or'
  opcode = DuckyOpcodes.OR

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_or():
        regset[reg] = v = regset[reg] | i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_or

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_or():
        regset[reg1] = v = regset[reg1] | regset[reg2]
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_or

class XOR(_BITOP):
  mnemonic = 'xor'
  opcode = DuckyOpcodes.XOR

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_xor():
        regset[reg] = v = regset[reg] ^ i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_xor

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_xor():
        regset[reg1] = v = regset[reg1] ^ regset[reg2]
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_xor

class SHL(_BITOP):
  mnemonic = 'shiftl'
  opcode = DuckyOpcodes.SHL

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = min(inst.sign_extend_immediate(core.LOGGER, inst), 32)

      if i == 0:
        def __jit_shiftl():
          v = regset[reg]
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftl

      elif i == 32:
        def __jit_shiftl():
          v = regset[reg] << i
          regset[reg] = 0
          core.arith_zero = True
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = False

        return __jit_shiftl

      else:
        def __jit_shiftl():
          v = regset[reg] << i
          regset[reg] = v % 4294967296
          core.arith_zero = (v & 0xFFFFFFFF) == 0
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftl

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_shiftl():
        i = min(regset[reg2], 32)

        if i == 0:
          v = regset[reg1]
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        elif i == 32:
          v = regset[reg1] << i
          regset[reg1] = 0
          core.arith_zero = True
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = False

        else:
          v = regset[reg1] << i
          regset[reg1] = v % 4294967296
          core.arith_zero = (v & 0xFFFFFFFF) == 0
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = (v & 0x80000000) != 0

      return __jit_shiftl

class SHR(_BITOP):
  mnemonic = 'shiftr'
  opcode = DuckyOpcodes.SHR

  @staticmethod
  def jit(core, inst):
    regset = core.registers

    if inst.immediate_flag == 1:
      reg = inst.reg1
      i = min(inst.sign_extend_immediate(core.LOGGER, inst), 32)

      if i == 0:
        def __jit_shiftr():
          v = regset[reg]
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftr

      elif i == 32:
        def __jit_shiftr():
          regset[reg] = 0
          core.arith_zero = True
          core.arith_overflow = core.arith_sign = False

        return __jit_shiftr

      else:
        def __jit_shiftr():
          regset[reg] = v = regset[reg] >> i
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

        return __jit_shiftr

    else:
      reg1, reg2 = inst.reg1, inst.reg2

      def __jit_shiftr():
        i = min(regset[reg2], 32)

        if i == 0:
          v = regset[reg1]
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        elif i == 32:
          regset[reg1] = 0
          core.arith_zero = True
          core.arith_overflow = core.arith_sign = False

        else:
          regset[reg1] = v = regset[reg1] >> i
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

      return __jit_shiftr

class SHRS(_BITOP):
  mnemonic = 'shiftrs'
  opcode = DuckyOpcodes.SHRS

class NOT(Descriptor_R):
  mnemonic = 'not'
  opcode = DuckyOpcodes.NOT
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = (~core.registers[inst.reg1]) % 4294967296
    update_arith_flags(core, core.registers[inst.reg1])


#
# Memory load/store operations
#
class CAS(Descriptor):
  mnemonic = 'cas'
  operands = 'r,r,r'
  opcode = DuckyOpcodes.CAS
  encoding = EncodingA

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])
    ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])
    ENCODE(logger, buffer, inst, 'reg3', 5, operands['register_n2'])

  @staticmethod
  def disassemble_operands(logger, inst):
    return [
      REGISTER_NAMES[inst.reg1],
      REGISTER_NAMES[inst.reg2],
      REGISTER_NAMES[inst.reg3]
    ]

  @staticmethod
  def execute(core, inst):
    core.arith_equal = False

    addr = core.registers[inst.reg1]
    actual_value = core.MEM_IN32(core.registers[inst.reg1])

    core.DEBUG('CAS.execute: value=%s', UINT32_FMT(actual_value))

    if actual_value == core.registers[inst.reg2]:
      core.MEM_OUT32(addr, core.registers[inst.reg3])
      core.arith_equal = True

    else:
      core.registers[inst.reg2] = actual_value

class _LOAD(Descriptor):
  operands = 'r,a'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])
    ENCODE(logger, buffer, inst, 'reg2', 5, operands['areg'])

    offset_immediate = operands.get('offset_immediate')
    if offset_immediate is not None:
      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)
      ENCODE(logger, buffer, inst, 'immediate', 15, int(offset_immediate))

  @staticmethod
  def disassemble_operands(logger, inst):
    operands = [REGISTER_NAMES[inst.reg1]]

    if inst.immediate_flag == 1:
      operands.append('%s[%s]' % (REGISTER_NAMES[inst.reg2], inst.sign_extend_immediate(logger, inst)))

    else:
      operands.append(REGISTER_NAMES[inst.reg2])

    return operands

  @staticmethod
  def execute(core, inst):
    regset, reg = core.registers, inst.reg1
    addr = RI_ADDR(core, inst, inst.reg2)

    if inst.opcode == DuckyOpcodes.LW:
      regset[reg] = core.MEM_IN32(addr)

    elif inst.opcode == DuckyOpcodes.LS:
      regset[reg] = core.MEM_IN16(addr)

    else:
      regset[reg] = core.MEM_IN8(addr)

    update_arith_flags(core, regset[reg])

  @staticmethod
  def jit(core, inst):
    regset, reg1, reg2 = core.registers, inst.reg1, inst.reg2

    if inst.opcode == DuckyOpcodes.LW:
      reader = core.MEM_IN32

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_lw():
            regset[reg1] = v = reader(regset[reg2])
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = (v & 0x80000000) != 0

          return __jit_lw

        else:
          def __jit_lw():
            regset[reg1] = v = reader((regset[reg2] + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = (v & 0x80000000) != 0

          return __jit_lw

      else:
        def __jit_lw():
          regset[reg1] = v = reader(regset[reg2])
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_lw

    elif inst.opcode == DuckyOpcodes.LS:
      reader = core.MEM_IN16

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_ls():
            regset[reg1] = v = reader(regset[reg2])
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_ls

        else:
          def __jit_ls():
            regset[reg1] = v = reader((regset[reg2] + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_ls

      else:
        def __jit_ls():
          regset[reg1] = v = reader(regset[reg2])
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

        return __jit_ls

    elif inst.opcode == DuckyOpcodes.LB:
      reader = core.MEM_IN8

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_lb():
            regset[reg1] = v = reader(regset[reg2])
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_lb

        else:
          def __jit_lb():
            regset[reg1] = v = reader((regset[reg2] + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_lb

      else:
        def __jit_lb():
          regset[reg1] = v = reader(regset[reg2])
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

        return __jit_lb

    return None

class _STORE(Descriptor):
  operands = 'a,r'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg1', 5, operands['areg'])
    ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])

    offset_immediate = operands.get('offset_immediate')
    if offset_immediate is not None:
      ENCODE(logger, buffer, inst, 'immediate_flag', 1, 1)
      ENCODE(logger, buffer, inst, 'immediate', 15, int(offset_immediate))

  @staticmethod
  def disassemble_operands(logger, inst):
    operands = []

    if inst.immediate_flag == 1:
      operands.append('%s[%s]' % (REGISTER_NAMES[inst.reg1], inst.sign_extend_immediate(logger, inst)))

    else:
      operands.append(REGISTER_NAMES[inst.reg1])

    operands.append(REGISTER_NAMES[inst.reg2])

    return operands

  @staticmethod
  def execute(core, inst):
    addr = RI_ADDR(core, inst, inst.reg1)

    if inst.opcode == DuckyOpcodes.STW:
      core.MEM_OUT32(addr, core.registers[inst.reg2])

    elif inst.opcode == DuckyOpcodes.STS:
      core.MEM_OUT16(addr, core.registers[inst.reg2] & 0xFFFF)

    else:
      core.MEM_OUT8(addr, core.registers[inst.reg2] & 0xFF)

  @staticmethod
  def jit(core, inst):
    reg1, reg2 = inst.reg1, inst.reg2
    regset = core.registers

    if inst.opcode == DuckyOpcodes.STW:
      writer = core.MEM_OUT32

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_stw():
            writer(regset[reg1], regset[reg2])

          return __jit_stw

        else:
          def __jit_stw():
            writer((regset[reg1] + offset) % 4294967296, regset[reg2])

          return __jit_stw

      else:
        def __jit_stw():
          writer(regset[reg1], regset[reg2])

        return __jit_stw

    elif inst.opcode == DuckyOpcodes.STS:
      writer = core.MEM_OUT16

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_sts():
            writer(regset[reg1], regset[reg2])

          return __jit_sts

        else:
          def __jit_sts():
            writer((regset[reg1] + offset) % 4294967296, regset[reg2])

          return __jit_sts

      else:
        def __jit_sts():
          writer(regset[reg1], regset[reg2])

        return __jit_sts

    elif inst.opcode == DuckyOpcodes.STB:
      writer = core.MEM_OUT8

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_stb():
            writer(regset[reg1], regset[reg2] & 0xFF)

          return __jit_stb

        else:
          def __jit_stb():
            writer((regset[reg1] + offset) % 4294967296, regset[reg2] & 0xFF)

          return __jit_stb

      else:
        def __jit_stb():
          writer(regset[reg1], regset[reg2] & 0xFF)

        return __jit_stb

    return None

class _LOAD_IMM(Descriptor_R_I):
  @classmethod
  def load(cls, core, inst):
    raise NotImplementedError('%s does not implement "load immediate" method' % cls.__name__)

  @classmethod
  def execute(cls, core, inst):
    cls.load(core, inst)
    update_arith_flags(core, core.registers[inst.reg])

class LW(_LOAD):
  mnemonic = 'lw'
  opcode = DuckyOpcodes.LW

class LS(_LOAD):
  mnemonic = 'ls'
  opcode = DuckyOpcodes.LS

class LB(_LOAD):
  mnemonic = 'lb'
  opcode = DuckyOpcodes.LB

class LI(_LOAD_IMM):
  mnemonic = 'li'
  opcode   = DuckyOpcodes.LI

  @classmethod
  def load(cls, core, inst):
    core.registers[inst.reg] = inst.sign_extend_immediate(core.LOGGER, inst)

  @staticmethod
  def jit(core, inst):
    regset, reg = core.registers, inst.reg
    i = inst.sign_extend_immediate(core.LOGGER, inst)

    if i == 0:
      def __jit_li():
        regset[reg] = 0
        core.arith_zero = True
        core.arith_overflow = False
        core.arith_sign = False

      return __jit_li

    else:
      sign = (i & 0x80000000) != 0

      def __jit_li():
        regset[reg] = i
        core.arith_zero = False
        core.arith_overflow = False
        core.arith_sign = sign

      return __jit_li

class LIU(_LOAD_IMM):
  mnemonic = 'liu'
  opcode   = DuckyOpcodes.LIU

  @classmethod
  def load(cls, core, inst):
    regset, reg = core.registers, inst.reg

    regset[reg] = (regset[reg] & 0xFFFF) | ((inst.sign_extend_immediate(core.LOGGER, inst) & 0xFFFF) << 16)

class LA(_LOAD_IMM):
  mnemonic = 'la'
  opcode   = DuckyOpcodes.LA
  relative_address = True

  @classmethod
  def load(cls, core, inst):
    core.registers[inst.reg] = (core.registers.ip + inst.sign_extend_immediate(core.LOGGER, inst)) % 4294967296

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    reg = inst.reg
    offset = inst.sign_extend_immediate(core.LOGGER, inst)

    if offset == 0:
      def __jit_la():
        regset[reg] = v = regset.ip
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_la

    else:
      def __jit_la():
        v = regset.ip + offset
        regset[reg] = v % 4294967296
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_la

class STW(_STORE):
  mnemonic = 'stw'
  opcode   = DuckyOpcodes.STW

class STS(_STORE):
  mnemonic = 'sts'
  opcode   = DuckyOpcodes.STS

class STB(_STORE):
  mnemonic = 'stb'
  opcode   = DuckyOpcodes.STB

class MOV(Descriptor_R_R):
  mnemonic = 'mov'
  opcode = DuckyOpcodes.MOV
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = core.registers[inst.reg2]

  @staticmethod
  def jit(core, inst):
    regset = core.registers
    reg1, reg2 = inst.reg1, inst.reg2

    def __jit_mov():
      regset[reg1] = regset[reg2]

    return __jit_mov

class SWP(Descriptor_R_R):
  mnemonic = 'swp'
  opcode = DuckyOpcodes.SWP
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    regset = core.registers

    regset[inst.reg1], regset[inst.reg2] = regset[inst.reg2], regset[inst.reg1]

  @staticmethod
  def jit(core, inst):
    reg1, reg2 = inst.reg1, inst.reg2
    regset = core.registers

    def __jit_swp():
      regset[reg1], regset[reg2] = regset[reg2], regset[reg1]

    return __jit_swp

#
# Control instructions
#
class CTR(Descriptor_R_R):
  mnemonic = 'ctr'
  opcode = DuckyOpcodes.CTR
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    core.registers[inst.reg1] = core.control_coprocessor.read(inst.reg2)
    update_arith_flags(core, core.registers[inst.reg1])

class CTW(Descriptor_R_R):
  mnemonic = 'ctw'
  opcode = DuckyOpcodes.CTW
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    core.control_coprocessor.write(inst.reg1, core.registers[inst.reg2])

class FPTC(Descriptor):
  mnemonic = 'fptc'
  opcode = DuckyOpcodes.FPTC
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.mmu.release_ptes()


class DuckyInstructionSet(InstructionSet):
  instruction_set_id = 0
  opcodes = DuckyOpcodes

NOP(DuckyInstructionSet)
INT(DuckyInstructionSet)
IPI(DuckyInstructionSet)
RETINT(DuckyInstructionSet)
CALL(DuckyInstructionSet)
RET(DuckyInstructionSet)
CLI(DuckyInstructionSet)
STI(DuckyInstructionSet)
HLT(DuckyInstructionSet)
RST(DuckyInstructionSet)
IDLE(DuckyInstructionSet)
PUSH(DuckyInstructionSet)
POP(DuckyInstructionSet)
INC(DuckyInstructionSet)
DEC(DuckyInstructionSet)
ADD(DuckyInstructionSet)
SUB(DuckyInstructionSet)
CMP(DuckyInstructionSet)
J(DuckyInstructionSet)
AND(DuckyInstructionSet)
OR(DuckyInstructionSet)
XOR(DuckyInstructionSet)
NOT(DuckyInstructionSet)
SHL(DuckyInstructionSet)
SHR(DuckyInstructionSet)
SHRS(DuckyInstructionSet)

# Memory access
LW(DuckyInstructionSet)
LS(DuckyInstructionSet)
LB(DuckyInstructionSet)
LI(DuckyInstructionSet)
LIU(DuckyInstructionSet)
LA(DuckyInstructionSet)
STW(DuckyInstructionSet)
STS(DuckyInstructionSet)
STB(DuckyInstructionSet)

MOV(DuckyInstructionSet)
SWP(DuckyInstructionSet)
MUL(DuckyInstructionSet)
DIV(DuckyInstructionSet)
UDIV(DuckyInstructionSet)
MOD(DuckyInstructionSet)
CMPU(DuckyInstructionSet)
CAS(DuckyInstructionSet)
SIS(DuckyInstructionSet)

# Branching instructions
BE(DuckyInstructionSet)
BNE(DuckyInstructionSet)
BZ(DuckyInstructionSet)
BNZ(DuckyInstructionSet)
BO(DuckyInstructionSet)
BNO(DuckyInstructionSet)
BS(DuckyInstructionSet)
BNS(DuckyInstructionSet)
BG(DuckyInstructionSet)
BGE(DuckyInstructionSet)
BL(DuckyInstructionSet)
BLE(DuckyInstructionSet)

# SET* instructions
SETE(DuckyInstructionSet)
SETNE(DuckyInstructionSet)
SETZ(DuckyInstructionSet)
SETNZ(DuckyInstructionSet)
SETO(DuckyInstructionSet)
SETNO(DuckyInstructionSet)
SETS(DuckyInstructionSet)
SETNS(DuckyInstructionSet)
SETG(DuckyInstructionSet)
SETGE(DuckyInstructionSet)
SETL(DuckyInstructionSet)
SETLE(DuckyInstructionSet)

# SEL* instructions
SELE(DuckyInstructionSet)
SELNE(DuckyInstructionSet)
SELZ(DuckyInstructionSet)
SELNZ(DuckyInstructionSet)
SELO(DuckyInstructionSet)
SELNO(DuckyInstructionSet)
SELS(DuckyInstructionSet)
SELNS(DuckyInstructionSet)
SELG(DuckyInstructionSet)
SELGE(DuckyInstructionSet)
SELL(DuckyInstructionSet)
SELLE(DuckyInstructionSet)

LPM(DuckyInstructionSet)

# Control instructions
CTR(DuckyInstructionSet)
CTW(DuckyInstructionSet)
FPTC(DuckyInstructionSet)

DuckyInstructionSet.init()

INSTRUCTION_SETS = {
  DuckyInstructionSet.instruction_set_id: DuckyInstructionSet
}

def get_instruction_set(i, exc = None):
  exc = exc or InvalidInstructionSetError

  if i not in INSTRUCTION_SETS:
    raise exc(i)

  return INSTRUCTION_SETS[i]
