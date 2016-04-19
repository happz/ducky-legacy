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
from ..errors import EncodingLargeValueError, UnalignedJumpTargetError, AccessViolationError, AssemblerError

PO_REGISTER  = r'(?P<register_n{operand_index}>(?:r\d\d?)|(?:sp)|(?:fp))'
PO_AREGISTER = r'(?P<address_register>r\d\d?|sp|fp)(?:\[(?:(?P<offset_sign>-|\+)?(?P<offset_immediate>0x[0-9a-fA-F]+|\d+))\])?'
PO_IMMEDIATE = r'(?:(?P<immediate>(?:-|\+)?(?:0x[0-9a-fA-F]+|\d+))|(?P<immediate_address>&[a-zA-Z_\.][a-zA-Z0-9_]*))'

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
      return ((ext_mask | i) & 0xFFFFFFFF) if i & sign_mask else i
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
    IE_FLAG('immediate_flag'),  # 15
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
    return '<EncodingC: opcode=%s, reg=%s, flag=%s, value=%s, immediate_flag=%s, immediate=%s>' % (self.opcode, self.reg, self.flag, self.value, self.immediate_flag, UINT16_FMT(self.immediate))

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
            k = -1 if 'offset_sign' in matches and matches['offset_sign'] and matches['offset_sign'].strip() == '-' else 1
            operands['offset_immediate'] = k * str2int(matches['offset_immediate'])

        elif 'immediate' in matches and matches['immediate']:
          operands['immediate'] = str2int(matches['immediate'])

        elif 'immediate_address' in matches and matches['immediate_address'] is not None:
          operands['immediate'] = matches['immediate_address']

        else:
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

class Descriptor_RI_R(Descriptor):
  operands = 'ri,r'
  encoding = EncodingR

  @staticmethod
  def assemble_operands(logger, buffer, inst, operands):
    from .assemble import Reference

    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg2', 5, operands['register_n1'])

    if 'register_n0' in operands:
      ENCODE(logger, buffer, inst, 'reg1', 5, operands['register_n0'])

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

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT16_FMT(inst.immediate), REGISTER_NAMES[inst.reg2]]

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
      from ..cpu import InvalidOpcodeError
      raise InvalidOpcodeError(opcode, ip = core.current_ip if core is not None else None, core = core)

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

    return u32_t(0x00000000 | inst.immediate).value

  return core.registers.map[getattr(inst, reg)].value

def RI_ADDR(core, inst, reg):
  core.DEBUG('RI_ADDR: inst=%s, reg=%s', inst, reg)

  base = core.registers.map[reg].value
  offset = inst.sign_extend_immediate(core.LOGGER, inst) if inst.immediate_flag == 1 else 0

  return u32_t(base + offset).value

def JUMP(core, inst):
  core.DEBUG('JUMP: inst=%s', inst)
  core.DEBUG('  IP=%s', UINT32_FMT(core.registers.ip.value))

  if inst.immediate_flag == 0:
    core.DEBUG('  register=%d, value=%s', inst.reg, UINT32_FMT(core.registers.map[inst.reg].value))
    core.registers.ip.value = core.registers.map[inst.reg].value

  else:
    v = inst.sign_extend_immediate(core.LOGGER, inst)
    nip = u32_t(core.registers.ip.value)
    nip.value += (v << 2)
    core.DEBUG('  offset=%s, aligned=%s, ip=%s, new=%s', UINT32_FMT(v), UINT32_FMT(v << 2), UINT32_FMT(core.registers.ip.value), UINT32_FMT(nip.value))
    core.registers.ip.value = nip.value

  core.DEBUG('JUMP: new ip=%s', UINT32_FMT(core.registers.ip.value))

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

  if reg.value == 0:
    core.arith_zero = True

  if reg.value & 0x80000000 != 0:
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
  SHIFTL = 38
  SHIFTR = 39

  OUTW   = 40
  OUTS   = 41
  OUTB   = 42
  INW    = 43
  INS    = 44
  INB    = 45

  # Branch instructions
  J      = 46

  # Condition instructions
  CMP    = 47
  CMPU   = 48
  SET    = 49
  BRANCH = 50

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
    core.do_int(RI_VAL(core, inst, 'reg'))

class IPI(Descriptor_R_RI):
  mnemonic = 'ipi'
  opcode = DuckyOpcodes.IPI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()

    cpuid = core.registers.map[inst.reg1].value
    cpuid, coreid = cpuid >> 16, cpuid & 0xFFFF

    core.cpu.machine.cpus[cpuid].cores[coreid].irq(RI_VAL(core, inst, 'reg2'))

class RETINT(Descriptor):
  mnemonic = 'retint'
  opcode   = DuckyOpcodes.RETINT
  encoding = EncodingI

  @staticmethod
  def execute(core, inst):
    core.check_protected_ins()
    core.exit_interrupt()

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

    JUMP(core, inst)

    if core.check_frames:
      core.frames[-1].IP = core.registers.ip.value

  @staticmethod
  def jit(core, inst):
    ip = core.registers.ip
    sp = core.registers.sp
    fp = core.registers.fp
    push = core.raw_push

    if inst.immediate_flag == 0:
      reg = core.registers.map[inst.reg]

      def __jit_call():
        push(ip.value)
        push(fp.value)
        fp.value = sp.value
        ip.value = reg.value

      return __jit_call

    else:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

      def __jit_call():
        push(ip.value)
        push(fp.value)
        fp.value = sp.value
        ip.value += i

      return __jit_call

class J(_JUMP):
  mnemonic = 'j'
  opcode   = DuckyOpcodes.J

  @staticmethod
  def execute(core, inst):
    JUMP(core, inst)

  @staticmethod
  def jit(core, inst):
    ip = core.registers.ip

    if inst.immediate_flag == 0:
      reg = core.registers.map[inst.reg]

      def __jit_j():
        ip.value = reg.value

      return __jit_j

    else:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

      def __jit_j():
        ip.value += i

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
    ip = core.registers.ip
    fp = core.registers.fp
    pop = core.raw_pop

    def __jit_ret():
      fp.value = pop()
      ip.value = pop()

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
    core.raw_push(RI_VAL(core, inst, 'reg'))

  @staticmethod
  def jit(core, inst):
    push = core.raw_push

    if inst.immediate_flag == 0:
      reg = core.registers.map[inst.reg]

      def __jit_push():
        push(reg.value)

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
    update_arith_flags(core, core.registers.map[inst.reg1])

  @staticmethod
  def jit(core, inst):
    pop = core.raw_pop
    reg = core.registers.map[inst.reg1]

    def __jit_pop():
      reg.value = v = pop()
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
    core.registers.map[inst.reg1].value += 1
    update_arith_flags(core, core.registers.map[inst.reg1])
    core.arith_overflow = core.registers.map[inst.reg1].value == 0

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg1]

    def __jit_inc():
      old, new = reg.value, reg.value + 1
      reg.value = new

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
    core.registers.map[inst.reg1].value -= 1
    update_arith_flags(core, core.registers.map[inst.reg1])

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg1]

    def __jit_dec():
      old, new = reg.value, reg.value - 1
      reg.value = new

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
    r = core.registers.map[inst.reg1]
    v = RI_VAL(core, inst, 'reg2')

    if inst.opcode == DuckyOpcodes.ADD:
      v = r.value + v

    elif inst.opcode == DuckyOpcodes.SUB:
      v = r.value - v

    elif inst.opcode == DuckyOpcodes.MUL:
      x = i32_t(r.value).value
      y = i32_t(v).value
      v = x * y

    elif inst.opcode == DuckyOpcodes.DIV:
      x = i32_t(r.value).value
      y = i32_t(v).value

      if abs(y) > abs(x):
        v = 0

      else:
        v = x // y

    elif inst.opcode == DuckyOpcodes.UDIV:
      x = u32_t(r.value).value
      y = u32_t(v).value

      v = x // y

    elif inst.opcode == DuckyOpcodes.MOD:
      x = i32_t(r.value).value
      y = i32_t(v).value

      v = x % y

    r.value = v
    update_arith_flags(core, r)

    if v > 0xFFFFFFFF:
      core.arith_overflow = True

class ADD(_BINOP):
  mnemonic = 'add'
  opcode = DuckyOpcodes.ADD

  @staticmethod
  def jit(core, inst):
    core.DEBUG('JIT: %s', inst)

    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_add():
        reg.value = v = reg.value + i
        core.arith_zero = reg.value == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_add

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_add():
        reg1.value = v = reg1.value + reg2.value
        core.arith_zero = reg1.value == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_add

class SUB(_BINOP):
  mnemonic = 'sub'
  opcode = DuckyOpcodes.SUB

  @staticmethod
  def jit(core, inst):
    core.DEBUG('JIT: %s', inst)

    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_sub():
        reg.value = v = reg.value - i
        core.arith_zero = reg.value == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_sub

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_sub():
        reg1.value = v = reg1.value - reg2.value
        core.arith_zero = reg1.value == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_sub

class MUL(_BINOP):
  mnemonic = 'mul'
  opcode = DuckyOpcodes.MUL

  @staticmethod
  def jit(core, inst):
    core.DEBUG('JIT: %s', inst)

    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = i32_t(inst.sign_extend_immediate(core.LOGGER, inst)).value

      def __jit_mul():
        reg.value = v = i32_t(reg.value).value * i
        core.arith_zero = reg.value == 0
        core.arith_overflow = v > 0xFFFFFFFF
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_mul

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_mul():
        reg1.value = v = i32_t(reg1.value).value * i32_t(reg2.value).value
        core.arith_zero = reg1.value == 0
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
  encoding = EncodingC

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

    return [str(inst.refers_to) if hasattr(inst, 'refers_to') and inst.refers_to is not None else UINT16_FMT(inst.immediate << 2)]

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
      JUMP(core, inst)

  @staticmethod
  def jit(core, inst):
    core.DEBUG('JIT: %s', inst)

    if inst.immediate_flag == 1:
      i = inst.sign_extend_immediate(core.LOGGER, inst) << 2

    else:
      reg = core.registers.map[inst.reg]

    ip = core.registers.ip

    if inst.flag in _COND.GFLAGS:
      if inst.flag == 0:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_ne():
              if core.arith_equal is False:
                ip.value = reg.value

            return __branch_ne

          else:
            def __branch_ne():
              if core.arith_equal is False:
                ip.value += i

            return __branch_ne

        else:
          if inst.immediate_flag == 0:
            def __branch_e():
              if core.arith_equal is True:
                ip.value = reg.value

            return __branch_e

          else:
            def __branch_e():
              if core.arith_equal is True:
                ip.value += i

            return __branch_e

      elif inst.flag == 1:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_nz():
              if core.arith_zero is False:
                ip.value = reg.value

            return __branch_nz

          else:
            def __branch_nz():
              if core.arith_zero is False:
                ip.value += i

            return __branch_nz

        else:
          if inst.immediate_flag == 0:
            def __branch_z():
              if core.arith_zero is True:
                ip.value = reg.value

            return __branch_z

          else:
            def __branch_z():
              if core.arith_zero is True:
                ip.value += i

            return __branch_z

      elif inst.flag == 2:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_no():
              if core.arith_overflow is False:
                ip.value = reg.value

            return __branch_no

          else:
            def __branch_no():
              if core.arith_overflow is False:
                ip.value += i

            return __branch_no

        else:
          if inst.immediate_flag == 0:
            def __branch_o():
              if core.arith_overflow is True:
                ip.value = reg.value

            return __branch_o

          else:
            def __branch_o():
              if core.arith_overflow is True:
                ip.value += i

            return __branch_o

      elif inst.flag == 3:
        if inst.value == 0:
          if inst.immediate_flag == 0:
            def __branch_ns():
              if core.arith_sign is False:
                ip.value = reg.value

            return __branch_ns

          else:
            def __branch_ns():
              if core.arith_sign is False:
                ip.value += i

            return __branch_ns

        else:
          if inst.immediate_flag == 0:
            def __branch_s():
              if core.arith_sign is True:
                ip.value = reg.value

            return __branch_s

          else:
            def __branch_s():
              if core.arith_sign is True:
                ip.value += i

            return __branch_s

    return None

class _SET(_COND):
  operands = 'r'
  opcode = DuckyOpcodes.SET

  @classmethod
  def assemble_operands(cls, logger, buffer, inst, operands):
    logger.debug('assemble_operands: inst=%s, operands=%s', inst, operands)

    ENCODE(logger, buffer, inst, 'reg', 5, operands['register_n0'])

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
    return [REGISTER_NAMES[inst.reg]]

  @staticmethod
  def disassemble_mnemonic(inst):
    if inst.flag in _COND.GFLAGS:
      return 'set%s%s' % ('n' if inst.value == 0 else '', _COND.MNEMONICS[inst.flag])

    else:
      return 'set%s%s' % (_COND.MNEMONICS[inst.flag], 'e' if inst.value == 1 else '')

  @staticmethod
  def execute(core, inst):
    core.registers.map[inst.reg].value = 1 if _COND.evaluate(core, inst) is True else 0
    update_arith_flags(core, core.registers.map[inst.reg])

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
    _CMP.evaluate(core, core.registers.map[inst.reg1].value, RI_VAL(core, inst, 'reg2'))

  @staticmethod
  def jit(core, inst):

    if inst.immediate_flag == 0:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_cmp():
        x = reg1.value
        y = reg2.value

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
      reg = core.registers.map[inst.reg1]
      y = inst.sign_extend_immediate(core.LOGGER, inst)
      y_signed = i32_t(y).value

      def __jit_cmp():
        x = reg.value

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
    _CMP.evaluate(core, core.registers.map[inst.reg1].value, RI_VAL(core, inst, 'reg2', sign_extend = False), signed = False)

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


#
# IO
#

class _IN(Descriptor_R_RI):
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    port = RI_VAL(core, inst, 'reg2')

    core.check_protected_port(port)

    r = core.registers.map[inst.reg1]
    dev = core.cpu.machine.ports[port]

    if inst.opcode == DuckyOpcodes.INB:
      r.value = dev.read_u8(port)

    elif inst.opcode == DuckyOpcodes.INS:
      r.value = dev.read_u16(port)

    else:
      r.value = dev.read_u32(port)

    update_arith_flags(core, r)

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg1]

    if inst.immediate_flag == 1:
      port = inst.sign_extend_immediate(core.LOGGER, inst)
      dev = core.cpu.machine.ports[port]
      is_protected = partial(dev.is_port_protected, port)

      if inst.opcode == DuckyOpcodes.INB:
        reader = dev.read_u8

        def __jit_inb():
          if not core.privileged and is_protected():
            raise AccessViolationError('Access to port not allowed in unprivileged mode: inst={}, port={}'.format(inst, port))

          reg.value = v = reader(port)
          core.arith_zero = v == 0
          core.arith_overflow = core.arith_sign = False

        return __jit_inb

    return None

class INB(_IN):
  mnemonic = 'inb'
  opcode   = DuckyOpcodes.INB

class INS(_IN):
  mnemonic = 'ins'
  opcode   = DuckyOpcodes.INS

class INW(_IN):
  mnemonic = 'inw'
  opcode   = DuckyOpcodes.INW

class _OUT(Descriptor_RI_R):
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    port = RI_VAL(core, inst, 'reg1')

    core.check_protected_port(port)

    r = core.registers.map[inst.reg2]
    dev = core.cpu.machine.ports[port]

    if inst.opcode == DuckyOpcodes.OUTB:
      dev.write_u8(port, r.value & 0xFF)

    elif inst.opcode == DuckyOpcodes.OUTS:
      dev.write_u16(port, r.value & 0xFFFF)

    else:
      dev.write_u32(port, r.value)

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg2]

    if inst.immediate_flag == 1:
      port = inst.sign_extend_immediate(core.LOGGER, inst)
      dev = core.cpu.machine.ports[port]
      is_protected = partial(dev.is_port_protected, port)

      if inst.opcode == DuckyOpcodes.OUTB:
        writer = dev.write_u8

        def __jit_outb():
          if not core.privileged and is_protected():
            raise AccessViolationError('Access to port not allowed in unprivileged mode: inst={}, port={}'.format(inst, port))

          writer(port, reg.value & 0xFF)

        return __jit_outb

    return None

class OUTB(_OUT):
  mnemonic      = 'outb'
  opcode = DuckyOpcodes.OUTB

class OUTW(_OUT):
  mnemonic = 'outw'
  opcode   = DuckyOpcodes.OUTW

class OUTS(_OUT):
  mnemonic = 'outs'
  opcode   = DuckyOpcodes.OUTS


#
# Bit operations
#
class _BITOP(Descriptor_R_RI):
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    r = core.registers.map[inst.reg1]
    v = RI_VAL(core, inst, 'reg2')

    if inst.opcode == DuckyOpcodes.AND:
      value = r.value & v

    elif inst.opcode == DuckyOpcodes.OR:
      value = r.value | v

    elif inst.opcode == DuckyOpcodes.XOR:
      value = r.value ^ v

    elif inst.opcode == DuckyOpcodes.SHIFTL:
      value = r.value << min(v, 32)

    elif inst.opcode == DuckyOpcodes.SHIFTR:
      value = r.value >> min(v, 32)

    r.value = value
    update_arith_flags(core, r)

    if value > 0xFFFFFFFF:
      core.arith_overflow = True

class AND(_BITOP):
  mnemonic = 'and'
  opcode = DuckyOpcodes.AND

  @staticmethod
  def jit(core, inst):
    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_and():
        reg.value = v = reg.value & i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_and

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_and():
        reg1.value = v = reg1.value & reg2.value
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_and

class OR(_BITOP):
  mnemonic = 'or'
  opcode = DuckyOpcodes.OR

  @staticmethod
  def jit(core, inst):
    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_or():
        reg.value = v = reg.value | i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_or

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_or():
        reg1.value = v = reg1.value | reg2.value
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_or

class XOR(_BITOP):
  mnemonic = 'xor'
  opcode = DuckyOpcodes.XOR

  @staticmethod
  def jit(core, inst):
    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = inst.sign_extend_immediate(core.LOGGER, inst)

      def __jit_xor():
        reg.value = v = reg.value ^ i
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_xor

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_xor():
        reg1.value = v = reg1.value ^ reg2.value
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_xor

class SHIFTL(_BITOP):
  mnemonic = 'shiftl'
  opcode = DuckyOpcodes.SHIFTL

  @staticmethod
  def jit(core, inst):
    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = min(inst.sign_extend_immediate(core.LOGGER, inst), 32)

      if i == 0:
        def __jit_shiftl():
          v = reg.value
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftl

      elif i == 32:
        def __jit_shiftl():
          v = reg.value << i
          reg.value = 0
          core.arith_zero = True
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = False

        return __jit_shiftl

      else:
        def __jit_shiftl():
          v = reg.value << i
          reg.value = v
          core.arith_zero = (v & 0xFFFFFFFF) == 0
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftl

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_shiftl():
        i = min(reg2.value, 32)

        if i == 0:
          v = reg1.value
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        elif i == 32:
          v = reg1.value << i
          reg1.value = 0
          core.arith_zero = True
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = False

        else:
          v = reg1.value << i
          reg1.value = v
          core.arith_zero = (v & 0xFFFFFFFF) == 0
          core.arith_overflow = (v & ~0xFFFFFFFF) != 0
          core.arith_sign = (v & 0x80000000) != 0

      return __jit_shiftl

class SHIFTR(_BITOP):
  mnemonic = 'shiftr'
  opcode = DuckyOpcodes.SHIFTR

  @staticmethod
  def jit(core, inst):
    if inst.immediate_flag == 1:
      reg = core.registers.map[inst.reg1]
      i = min(inst.sign_extend_immediate(core.LOGGER, inst), 32)

      if i == 0:
        def __jit_shiftr():
          v = reg.value
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        return __jit_shiftr

      elif i == 32:
        def __jit_shiftr():
          reg.value = 0
          core.arith_zero = True
          core.arith_overflow = core.arith_sign = False

        return __jit_shiftr

      else:
        def __jit_shiftr():
          reg.value = v = reg.value >> i
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

        return __jit_shiftr

    else:
      reg1 = core.registers.map[inst.reg1]
      reg2 = core.registers.map[inst.reg2]

      def __jit_shiftr():
        i = min(reg2.value, 32)

        if i == 0:
          v = reg1.value
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = (v & 0x80000000) != 0

        elif i == 32:
          reg1.value = 0
          core.arith_zero = True
          core.arith_overflow = core.arith_sign = False

        else:
          reg1.value = v = reg1.value >> i
          core.arith_zero = v == 0
          core.arith_overflow = False
          core.arith_sign = False

      return __jit_shiftr

class NOT(Descriptor_R):
  mnemonic = 'not'
  opcode = DuckyOpcodes.NOT
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    r = core.registers.map[inst.reg1]

    r.value = ~r.value
    update_arith_flags(core, r)


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

    reg1, reg2, reg3 = core.registers.map[inst.reg1], core.registers.map[inst.reg2], core.registers.map[inst.reg3]
    core.DEBUG('CAS.execute: reg1=%s (%s), reg2=%s (%s), reg3=%s (%s)', inst.reg1, UINT32_FMT(reg1.value), inst.reg2, UINT32_FMT(reg2.value), inst.reg3, UINT32_FMT(reg3.value))

    addr = core.registers.map[inst.reg1].value
    actual_value = core.MEM_IN32(reg1.value)

    core.DEBUG('CAS.execute: value=%s', UINT32_FMT(actual_value))

    if actual_value == reg2.value:
      core.MEM_OUT32(addr, reg3.value)
      core.arith_equal = True

    else:
      reg2.value = actual_value

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
    r = core.registers.map[inst.reg1]
    addr = RI_ADDR(core, inst, inst.reg2)

    if inst.opcode == DuckyOpcodes.LW:
      r.value = core.MEM_IN32(addr)

    elif inst.opcode == DuckyOpcodes.LS:
      r.value = core.MEM_IN16(addr)

    else:
      r.value = core.MEM_IN8(addr)

    update_arith_flags(core, r)

  @staticmethod
  def jit(core, inst):
    reg1 = core.registers.map[inst.reg1]
    reg2 = core.registers.map[inst.reg2]

    if inst.opcode == DuckyOpcodes.LW:
      reader = core.MEM_IN32

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_lw():
            reg1.value = v = reader(reg2.value)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = (v & 0x80000000) != 0

          return __jit_lw

        else:
          def __jit_lw():
            reg1.value = v = reader((reg2.value + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = (v & 0x80000000) != 0

          return __jit_lw

      else:
        def __jit_lw():
          reg1.value = v = reader(reg2.value)
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
            reg1.value = v = reader(reg2.value)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_ls

        else:
          def __jit_ls():
            reg1.value = v = reader((reg2.value + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_ls

      else:
        def __jit_ls():
          reg1.value = v = reader(reg2.value)
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
            reg1.value = v = reader(reg2.value)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_lb

        else:
          def __jit_lb():
            reg1.value = v = reader((reg2.value + offset) % 4294967296)
            core.arith_zero = v == 0
            core.arith_overflow = False
            core.arith_sign = False

          return __jit_lb

      else:
        def __jit_lb():
          reg1.value = v = reader(reg2.value)
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
      core.MEM_OUT32(addr, core.registers.map[inst.reg2].value)

    elif inst.opcode == DuckyOpcodes.STS:
      core.MEM_OUT16(addr, core.registers.map[inst.reg2].value & 0xFFFF)

    else:
      core.MEM_OUT8(addr, core.registers.map[inst.reg2].value & 0xFF)

  @staticmethod
  def jit(core, inst):
    reg1 = core.registers.map[inst.reg1]
    reg2 = core.registers.map[inst.reg2]

    if inst.opcode == DuckyOpcodes.STW:
      writer = core.MEM_OUT32

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_stw():
            writer(reg1.value, reg2.value)

          return __jit_stw

        else:
          def __jit_stw():
            writer((reg1.value + offset) % 4294967296, reg2.value)

          return __jit_stw

      else:
        def __jit_stw():
          writer(reg1.value, reg2.value)

        return __jit_stw

    elif inst.opcode == DuckyOpcodes.STS:
      writer = core.MEM_OUT16

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_sts():
            writer(reg1.value, reg2.value)

          return __jit_sts

        else:
          def __jit_sts():
            writer((reg1.value + offset) % 4294967296, reg2.value)

          return __jit_sts

      else:
        def __jit_sts():
          writer(reg1.value, reg2.value)

        return __jit_sts

    elif inst.opcode == DuckyOpcodes.STB:
      writer = core.MEM_OUT8

      if inst.immediate_flag == 1:
        offset = inst.sign_extend_immediate(core.LOGGER, inst)

        if offset == 0:
          def __jit_stb():
            writer(reg1.value, reg2.value & 0xFF)

          return __jit_stb

        else:
          def __jit_stb():
            writer((reg1.value + offset) % 4294967296, reg2.value & 0xFF)

          return __jit_stb

      else:
        def __jit_stb():
          writer(reg1.value, reg2.value & 0xFF)

        return __jit_stb

    return None

class _LOAD_IMM(Descriptor_R_I):
  @classmethod
  def load(cls, core, inst):
    raise NotImplementedError('%s does not implement "load immediate" method' % cls.__name__)

  @classmethod
  def execute(cls, core, inst):
    cls.load(core, inst)
    update_arith_flags(core, core.registers.map[inst.reg])

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
    core.registers.map[inst.reg].value = inst.sign_extend_immediate(core.LOGGER, inst)

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg]
    i = inst.sign_extend_immediate(core.LOGGER, inst)

    if i == 0:
      def __jit_li():
        reg.value = 0
        core.arith_zero = True
        core.arith_overflow = False
        core.arith_sign = False

      return __jit_li

    else:
      sign = (i & 0x80000000) != 0

      def __jit_li():
        reg.value = i
        core.arith_zero = False
        core.arith_overflow = False
        core.arith_sign = sign

      return __jit_li

class LIU(_LOAD_IMM):
  mnemonic = 'liu'
  opcode   = DuckyOpcodes.LIU

  @classmethod
  def load(cls, core, inst):
    r = core.registers.map[inst.reg]

    r.value = (r.value & 0xFFFF) | ((inst.sign_extend_immediate(core.LOGGER, inst) & 0xFFFF) << 16)

class LA(_LOAD_IMM):
  mnemonic = 'la'
  opcode   = DuckyOpcodes.LA
  relative_address = True

  @classmethod
  def load(cls, core, inst):
    core.registers.map[inst.reg].value = core.registers.ip.value + inst.sign_extend_immediate(core.LOGGER, inst)

  @staticmethod
  def jit(core, inst):
    reg = core.registers.map[inst.reg]
    ip = core.registers.ip
    offset = inst.sign_extend_immediate(core.LOGGER, inst)

    if offset == 0:
      def __jit_la():
        reg.value = v = ip.value
        core.arith_zero = v == 0
        core.arith_overflow = False
        core.arith_sign = (v & 0x80000000) != 0

      return __jit_la

    else:
      def __jit_la():
        reg.value = v = ip.value + offset
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
    core.registers.map[inst.reg1].value = core.registers.map[inst.reg2].value

  @staticmethod
  def jit(core, inst):
    reg1 = core.registers.map[inst.reg1]
    reg2 = core.registers.map[inst.reg2]

    def __jit_mov():
      reg1.value = reg2.value

    return __jit_mov

class SWP(Descriptor_R_R):
  mnemonic = 'swp'
  opcode = DuckyOpcodes.SWP
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    r1 = core.registers.map[inst.reg1]
    r2 = core.registers.map[inst.reg2]

    r1.value, r2.value = r2.value, r1.value

  @staticmethod
  def jit(core, inst):
    reg1 = core.registers.map[inst.reg1]
    reg2 = core.registers.map[inst.reg2]

    def __jit_swp():
      reg1.value, reg2.value = reg2.value, reg1.value

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
    core.registers.map[inst.reg1].value = core.control_coprocessor.read(inst.reg2)
    update_arith_flags(core, core.registers.map[inst.reg1])

class CTW(Descriptor_R_R):
  mnemonic = 'ctw'
  opcode = DuckyOpcodes.CTW
  encoding = EncodingR

  @staticmethod
  def execute(core, inst):
    core.control_coprocessor.write(inst.reg1, core.registers.map[inst.reg2].value)

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
INW(DuckyInstructionSet)
INB(DuckyInstructionSet)
INS(DuckyInstructionSet)
OUTS(DuckyInstructionSet)
OUTW(DuckyInstructionSet)
OUTB(DuckyInstructionSet)
AND(DuckyInstructionSet)
OR(DuckyInstructionSet)
XOR(DuckyInstructionSet)
NOT(DuckyInstructionSet)
SHIFTL(DuckyInstructionSet)
SHIFTR(DuckyInstructionSet)

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
  from ..cpu import InvalidInstructionSetError
  exc = exc or InvalidInstructionSetError

  if i not in INSTRUCTION_SETS:
    raise exc(i)

  return INSTRUCTION_SETS[i]
