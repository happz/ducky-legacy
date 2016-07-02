import logging
import os

from functools import partial
from six import iteritems, integer_types

import ducky.cpu.registers
from ducky.cpu.assemble import SourceLocation
from ducky.cpu.instructions import DuckyInstructionSet
from ducky.cpu.registers import REGISTER_NAMES
from ducky.errors import UnalignedJumpTargetError, DivideByZeroError, PrivilegedInstructionError, InvalidExceptionError
from ducky.mm import u32_t, i32_t

from . import LOGGER, PYPY

from hypothesis import given, example, assume
from hypothesis.strategies import integers, lists, booleans, composite


CORE = None
BUFFER = None

def setup():
  from ducky.cpu import CPU
  from ducky.machine import Machine
  from ducky.mm import MemoryController
  from ducky.config import MachineConfig

  machine = Machine(logger = logging.getLogger())
  machine.config = MachineConfig()
  machine.memory = mm = MemoryController(machine, size = 0x100000000)
  cpu = CPU(machine, 0, mm)

  global CORE
  CORE = cpu.cores[0]

  global LOGGER
  LOGGER.setLevel(logging.DEBUG)

  class SimpleBuffer(object):
    def get_error(self, cls, info, column = None, length = None, **kwargs):
      kwargs['location'] = SourceLocation(filename = '<unknown>', lineno = 0)
      kwargs['info'] = info

      raise cls(**kwargs)

  global BUFFER
  BUFFER = SimpleBuffer()

def sign_extend(sign_mask, ext_mask, value):
  LOGGER.debug('sign_extend: sign_mask=%s, ext_mas=%s, value=%s', sign_mask, ext_mask, value)

  return u32_t(ext_mask | value).value if value & sign_mask else u32_t(value).value

sign_extend11 = partial(sign_extend, 0x400,   0xFFFF8000)
sign_extend15 = partial(sign_extend, 0x4000,  0xFFFF8000)
sign_extend20 = partial(sign_extend, 0x80000, 0xFFF00000)

def encode_inst(desc, operands):
  inst = desc.encoding()
  inst.opcode = desc.opcode
  desc.assemble_operands(LOGGER, BUFFER, inst, operands)
  LOGGER.debug('TEST: inst=%s' % DuckyInstructionSet.disassemble_instruction(LOGGER, inst))

  return inst

JIT = os.environ.get('JIT', 'no') == 'yes'

if JIT:
  def normal_execute_inst(core, inst_class, inst):
    inst_class.execute(core, inst)

  def execute_inst(core, inst_class, inst):
    fn = inst_class.jit(core, inst)

    if fn is None:
      normal_execute_inst(core, inst_class, inst)

    else:
      fn()

else:
  def execute_inst(core, inst_class, inst):
    inst_class.execute(core, inst)

class CoreState(object):
  register_names = REGISTER_NAMES
  flag_names =  ['privileged', 'hwint_allowed', 'arith_equal', 'arith_zero', 'arith_overflow', 'arith_sign', 'alive', 'running', 'idle']
  flag_arith = ['equal', 'zero', 'overflow', 'sign']

  def __init__(self, registers, flags, exit_code):
    self.registers = registers
    self.flags = flags
    self.exit_code = exit_code

  def clone(self):
    return CoreState(self.registers, self.flags, self.exit_code)

  def reset(self, core = None):
    core = core or CORE

    core.reset()

    for i, value in enumerate(self.registers):
      core.registers.map[i].value = value

    for flag, value in zip(CoreState.flag_names, self.flags):
      setattr(core, flag, value)

    core.exit_code = self.exit_code

  def __repr__(self):
    l = []

    l += ['%s=0x%08X' % (name, value) for name, value in zip(CoreState.register_names, self.registers) if value != 0]
    l += ['%s=%s' % (name, value) for name, value in zip(list('PHEZOSARI'), self.flags) if value is not False]

    return ', '.join(l)

  def __getattr__(self, name):
    if name in CoreState.register_names:
      return self.registers[CoreState.register_names.index(name)]

    if name in CoreState.flag_names:
      return self.flags[CoreState.flag_names.index(name)]

    if name in CoreState.flag_arith:
      return self.flags[CoreState.flag_names.index('arith_' + name)]

    raise AttributeError(name)

  def __setattr__(self, name, value):
    if name in CoreState.register_names:
      self.registers[CoreState.register_names.index(name)] = value
      return

    if name in CoreState.flag_names:
      self.flags[CoreState.flag_names.index(name)] = value
      return

    if name in CoreState.flag_arith:
      self.flags[CoreState.flag_names.index('arith_' + name)] = value
      return

    super(CoreState, self).__setattr__(name, value)

  def check(self, *args, **kwargs):
    container = self.clone()

    for name, value in args:
      if isinstance(name, integer_types):
        setattr(container, CoreState.register_names[name], value)

      elif name in CoreState.flag_names:
        setattr(container, name, value)

      else:
        raise AttributeError(name)

    for name, value in iteritems(kwargs):
      setattr(container, name, value)

    LOGGER.debug('EXPECT: %r', container)

    # Assert registers
    expected = [getattr(container, reg) for reg in CoreState.register_names]
    actual   = [CORE.registers.map[i].value for i, reg in enumerate(CoreState.register_names)]

    for reg, expected_value, actual_value in zip(CoreState.register_names, expected, actual):
      if actual_value == expected_value:
        continue

      LOGGER.error('Register %s mismatch: 0x%08X expected, 0x%08X found', reg, expected_value, actual_value)
      assert False

    # Assert flags
    names    = list('PHEZOSARI')
    expected = [getattr(container, flag) for flag in CoreState.flag_names]
    actual   = [CORE.privileged, CORE.hwint_allowed, CORE.arith_equal, CORE.arith_zero, CORE.arith_overflow, CORE.arith_sign, CORE.alive, CORE.running, CORE.idle]

    for flag, expected_value, actual_value in zip(names, expected, actual):
      if actual_value == expected_value:
        continue

      LOGGER.error('Flag %s has unexpected value: %s expected, %s found', flag, expected_value, actual_value)
      assert False

  def flags_to_int(self):
    u = 0

    for i, name in enumerate(['privileged', 'hwint_allowed', 'equal', 'zero', 'overflow', 'sign']):
      if getattr(self, name) is True:
        u |= (1 << i)

    return u

  def flags_from_int(self, u):
    for i, name in enumerate(['privileged', 'hwint_allowed', 'equal', 'zero', 'overflow', 'sign']):
      setattr(self, name, True if u & (1 << i) else False)


REGISTER    = integers(min_value = 0, max_value = 31)
VALUE       = integers(min_value = 0, max_value = 0xFFFFFFFF)
VALUE16     = integers(min_value = 0, max_value = 0xFFFF)
VALUE8      = integers(min_value = 0, max_value = 0xFF)
IMMEDIATE11 = integers(min_value = 0, max_value = 0x7FF)
IMMEDIATE15 = integers(min_value = 0, max_value = 0x7FFF)
IMMEDIATE20 = integers(min_value = 0, max_value = 0xFFFFF)

@composite
def __STATE(draw):
  return CoreState(draw(lists(VALUE, min_size = ducky.cpu.registers.Registers.REGISTER_COUNT, max_size = ducky.cpu.registers.Registers.REGISTER_COUNT)), draw(lists(booleans(), min_size = 9, max_size = 9)), draw(VALUE))

STATE = __STATE()


def __base_setting_test(state, reg, inst_class = None, cond = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d', state, reg)

  inst = encode_inst(inst_class, {'register_n0': reg})

  expected_value = 1 if cond(state) else 0

  state.reset()

  execute_inst(CORE, inst_class, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign = False)

def __base_select_test_immediate(state, reg, tv, fv, inst_class = None, cond = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, tv=0x%08X, fv=0x%08X', state, reg, tv, fv)

  inst = encode_inst(inst_class, {'register_n0': reg, 'immediate': fv})

  expected_value = tv if cond(state) else fv

  state.reset()
  CORE.registers.map[reg].value = tv

  execute_inst(CORE, inst_class, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign = (expected_value & 0x80000000) != 0)

def __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = None, cond = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=1%d, reg2=%d, tv=0x%08X, fv=0x%08X', state, reg1, reg2, tv, fv)

  inst = encode_inst(inst_class, {'register_n0': reg1, 'register_n1': reg2})

  expected_value = fv if reg1 == reg2 else (tv if cond(state) else fv)

  state.reset()
  CORE.registers.map[reg1].value = tv
  CORE.registers.map[reg2].value = fv

  execute_inst(CORE, inst_class, inst)

  state.check((reg1, expected_value), (reg2, fv), zero = expected_value == 0, overflow = False, sign = (expected_value & 0x80000000) != 0)

def __base_branch_test_immediate(state, offset, inst_class = None, cond = None):
  state.ip &= 0xFFFFFFFC
  offset &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, offset=0x%08X', state, offset)

  inst = encode_inst(inst_class, {'immediate': offset})

  expected_value = ((state.ip + sign_extend11(offset // 4) * 4) % (2 ** 32)) if cond(state) else state.ip

  state.reset()

  execute_inst(CORE, inst_class, inst)

  state.check(ip = expected_value)

def __base_branch_test_register(state, reg, addr, inst_class = None, cond = None):
  state.ip &= 0xFFFFFFFC
  addr &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, addr=0x%08X', state, reg, addr)

  inst = encode_inst(inst_class, {'register_n0': reg})

  expected_value = addr if cond(state) else state.ip

  state.reset()
  CORE.registers.map[reg].value = addr

  execute_inst(CORE, inst_class, inst)

  state.check((reg, addr), ip = expected_value)

def __base_arith_test_immediate(state, reg, a, b, inst_class = None, compute = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X, b=0x%08X', state, reg, a, b)

  inst = encode_inst(inst_class, {'register_n0': reg, 'immediate': b})

  value, expected_value = compute(state, reg, a, b)

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, inst_class, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = value > 0xFFFFFFFF, sign = expected_value & 0x80000000 != 0)

def __base_arith_test_register(state, reg1, reg2, a, b, inst_class = None, compute = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X, b=0x%08X', state, reg1, reg2, a, b)

  inst = encode_inst(inst_class, {'register_n0': reg1, 'register_n1': reg2})

  value, expected_value = compute(state, reg1, reg2, a, b)

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  execute_inst(CORE, inst_class, inst)

  state.check((reg1, expected_value), (reg2, expected_value if reg1 == reg2 else b), zero = expected_value == 0, overflow = value > 0xFFFFFFFF, sign = expected_value & 0x80000000 != 0)

def __base_arith_by_zero_immediate(state, reg, a, inst_class = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X', state, reg, a)

  b = 0
  inst = encode_inst(inst_class, {'register_n0': reg, 'immediate': b})

  state.reset()
  CORE.registers.map[reg].value = a

  try:
    execute_inst(CORE, inst_class, inst)

  except DivideByZeroError:
    pass

  else:
    assert 'Instruction expected to divide by zero'

  state.check((reg, a))

def __base_arith_by_zero_register(state, reg1, reg2, a, inst_class = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X', state, reg1, reg2, a)

  b = 0
  inst = encode_inst(inst_class, {'register_n0': reg1, 'register_n1': reg2})

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  try:
    execute_inst(CORE, inst_class, inst)

  except DivideByZeroError:
    pass

  else:
    assert 'Instruction expected to divide by zero'

  state.check((reg1, a), (reg2, b))

def __base_load_test(state, reg1, reg2, address, value, inst_class, size, offset = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, address=0x%08X, value=0x%08X, offset=%s', state, reg1, reg2, address, value, 'None' if offset is None else '0x%08X' % offset)

  # reset machine, to get clear memory
  setup()

  operands = {
    'register_n0': reg1,
    'areg': reg2
  }

  if offset is not None:
    operands['offset_immediate'] = offset

  offset = sign_extend15(offset or 0)
  memory_address = u32_t(address + offset).value

  inst = encode_inst(inst_class, operands)

  state.reset()
  CORE.registers.map[reg2].value = address

  if size == 1:
    CORE.mmu.memory.write_u8(memory_address, value)

  elif size == 2:
    CORE.mmu.memory.write_u16(memory_address, value)

  else:
    CORE.mmu.memory.write_u32(memory_address, value)

  execute_inst(CORE, inst_class, inst)

  state.check((reg1, value), (reg2, value if reg1 == reg2 else address), zero = value == 0, overflow = False, sign = (value & 0x80000000) != 0)

def __base_store_test(state, reg1, reg2, address, value, inst_class, size, offset = None):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, address=0x%08X, value=0x%08X, offset=%s, inst=%s, size=%d', state, reg1, reg2, address, value, 'None' if offset is None else '0x%08X' % offset, inst_class, size)

  # reset machine, to get clear memory
  setup()

  operands = {
    'areg': reg1,
    'register_n1': reg2
  }

  if offset is not None:
    operands['offset_immediate'] = offset

  offset = sign_extend15(offset or 0)
  memory_address = u32_t(address + offset).value

  expected_value = (value & 0xFF) if size == 1 else ((value & 0xFFFF) if size == 2 else value)

  inst = encode_inst(inst_class, operands)

  state.reset()
  CORE.registers.map[reg1].value = address

  if reg1 != reg2:
    CORE.registers.map[reg2].value = value

  execute_inst(CORE, inst_class, inst)

  regs = [(reg1, address)]
  if reg1 != reg2:
    regs.append((reg2, value))

  state.check(*regs)

  reader = CORE.MEM_IN8 if size == 1 else (CORE.MEM_IN16 if size == 2 else CORE.MEM_IN32)

  memory_value = reader(memory_address)
  assert expected_value == memory_value, 'Memory contains 0x%08X, 0x%08X expected' % (memory_value, value)


#
# ADD
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0xFFFFFFFE, b = 2)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0xFFFFFFFE, b = 4)
def test_add_immediate(state, reg, a, b):
  from ducky.cpu.instructions import ADD

  def compute(state, reg, a, b):
    value = a + sign_extend15(b)
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = ADD, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), a = 0xFFFFFFFE, b = 2)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), a = 0xFFFFFFFE, b = 4)
def test_add_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import ADD

  def compute(state, reg1, reg2, a, b):
    value = 2 * b if reg1 == reg2 else a + b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = ADD, compute = compute)


#
# AND
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_and_immediate(state, reg, a, b):
  from ducky.cpu.instructions import AND

  def compute(state, reg, a, b):
    value = a & sign_extend15(b)
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = AND, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_and_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import AND

  def compute(state, reg1, reg2, a, b):
    value = b if reg1 == reg2 else a & b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = AND, compute = compute)


#
# Branching - B*
#
@given(offset = IMMEDIATE11)
def test_branch_unaligned(offset):
  from ducky.cpu.instructions import BE

  assume(offset & 0x3 != 0)

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: offset=0x%08X' % offset)

  try:
    encode_inst(BE, {'immediate': offset})

  except UnalignedJumpTargetError:
    pass

  else:
    assert False, 'Encoding expected to raise an error with un-aligned offset'


#
# BE
#
@given(state = STATE, offset = IMMEDIATE11)
def test_be_immediate(state, offset):
  from ducky.cpu.instructions import BE

  __base_branch_test_immediate(state, offset, inst_class = BE, cond = lambda f: f.equal is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_be_register(state, reg, addr):
  from ducky.cpu.instructions import BE

  __base_branch_test_register(state, reg, addr, inst_class = BE, cond = lambda f: f.equal is True)


#
# BG
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bg_immediate(state, offset):
  from ducky.cpu.instructions import BG

  __base_branch_test_immediate(state, offset, inst_class = BG, cond = lambda f: f.sign is False and f.equal is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bg_register(state, reg, addr):
  from ducky.cpu.instructions import BG

  __base_branch_test_register(state, reg, addr, inst_class = BG, cond = lambda f: f.sign is False and f.equal is False)


#
# BGE
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bge_immediate(state, offset):
  from ducky.cpu.instructions import BGE

  __base_branch_test_immediate(state, offset, inst_class = BGE, cond = lambda f: f.sign is False or f.equal is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bge_register(state, reg, addr):
  from ducky.cpu.instructions import BGE

  __base_branch_test_register(state, reg, addr, inst_class = BGE, cond = lambda f: f.sign is False or f.equal is True)


#
# BL
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bl_immediate(state, offset):
  from ducky.cpu.instructions import BL

  __base_branch_test_immediate(state, offset, inst_class = BL, cond = lambda f: f.sign is True and f.equal is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bl_register(state, reg, addr):
  from ducky.cpu.instructions import BL

  __base_branch_test_register(state, reg, addr, inst_class = BL, cond = lambda f: f.sign is True and f.equal is False)


#
# BLE
#
@given(state = STATE, offset = IMMEDIATE11)
def test_ble_immediate(state, offset):
  from ducky.cpu.instructions import BLE

  __base_branch_test_immediate(state, offset, inst_class = BLE, cond = lambda f: f.sign is True or f.equal is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_ble_register(state, reg, addr):
  from ducky.cpu.instructions import BLE

  __base_branch_test_register(state, reg, addr, inst_class = BLE, cond = lambda f: f.sign is True or f.equal is True)


#
# BNE
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bne_immediate(state, offset):
  from ducky.cpu.instructions import BNE

  __base_branch_test_immediate(state, offset, inst_class = BNE, cond = lambda f: f.equal is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bne_register(state, reg, addr):
  from ducky.cpu.instructions import BNE

  __base_branch_test_register(state, reg, addr, inst_class = BNE, cond = lambda f: f.equal is False)


#
# BNO
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bno_immediate(state, offset):
  from ducky.cpu.instructions import BNO

  __base_branch_test_immediate(state, offset, inst_class = BNO, cond = lambda f: f.overflow is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bno_register(state, reg, addr):
  from ducky.cpu.instructions import BNO

  __base_branch_test_register(state, reg, addr, inst_class = BNO, cond = lambda f: f.overflow is False)


#
# BNS
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bns_immediate(state, offset):
  from ducky.cpu.instructions import BNS

  __base_branch_test_immediate(state, offset, inst_class = BNS, cond = lambda f: f.sign is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bns_register(state, reg, addr):
  from ducky.cpu.instructions import BNS

  __base_branch_test_register(state, reg, addr, inst_class = BNS, cond = lambda f: f.sign is False)


#
# BNZ
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bnz_immediate(state, offset):
  from ducky.cpu.instructions import BNZ

  __base_branch_test_immediate(state, offset, inst_class = BNZ, cond = lambda f: f.zero is False)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bnz_register(state, reg, addr):
  from ducky.cpu.instructions import BNZ

  __base_branch_test_register(state, reg, addr, inst_class = BNZ, cond = lambda f: f.zero is False)


#
# BO
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bo_immediate(state, offset):
  from ducky.cpu.instructions import BO

  __base_branch_test_immediate(state, offset, inst_class = BO, cond = lambda f: f.overflow is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bo_register(state, reg, addr):
  from ducky.cpu.instructions import BO

  __base_branch_test_register(state, reg, addr, inst_class = BO, cond = lambda f: f.overflow is True)


#
# BS
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bs_immediate(state, offset):
  from ducky.cpu.instructions import BS

  __base_branch_test_immediate(state, offset, inst_class = BS, cond = lambda f: f.sign is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bs_register(state, reg, addr):
  from ducky.cpu.instructions import BS

  __base_branch_test_register(state, reg, addr, inst_class = BS, cond = lambda f: f.sign is True)


#
# BZ
#
@given(state = STATE, offset = IMMEDIATE11)
def test_bz_immediate(state, offset):
  from ducky.cpu.instructions import BZ

  __base_branch_test_immediate(state, offset, inst_class = BZ, cond = lambda f: f.zero is True)

@given(state = STATE, reg = REGISTER, addr = VALUE)
def test_bz_register(state, reg, addr):
  from ducky.cpu.instructions import BZ

  __base_branch_test_register(state, reg, addr, inst_class = BZ, cond = lambda f: f.zero is True)


#
# CALL
#
@given(state = STATE, ip = VALUE, offset = IMMEDIATE20)
def test_call_immediate(state, ip, offset):
  from ducky.cpu.instructions import CALL

  state.sp &= 0xFFFFFFFC
  ip &= 0xFFFFFFFC
  offset &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, ip=0x%08X, offset=0x%08X', state, ip, offset)

  inst = encode_inst(CALL, {'immediate': offset})

  expected_value = (ip + sign_extend20(offset // 4) * 4) % (2 ** 32)

  state.reset()
  CORE.registers.ip.value = ip

  execute_inst(CORE, CALL, inst)

  state.check(ip = expected_value, fp = u32_t(state.sp - 8).value, sp = u32_t(state.sp - 8).value)


@given(state = STATE, ip = VALUE, reg = REGISTER, addr = VALUE)
def test_call_register(state, ip, reg, addr):
  from ducky.cpu.instructions import CALL

  state.sp &= 0xFFFFFFFC
  ip &= 0xFFFFFFFC
  addr &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, ip=0x%08X, reg=%d, addr=0x%08X', state, ip, reg, addr)

  inst = encode_inst(CALL, {'register_n0': reg})

  expected_ip = addr
  expected_fp = u32_t(state.sp - 8).value
  expected_sp = u32_t(state.sp - 8).value

  if reg == 30:
    expected_ip = expected_fp

  elif reg == 31:
    expected_ip = expected_fp = expected_sp = u32_t(addr - 8).value

  state.reset()
  CORE.registers.ip.value = ip
  CORE.registers.map[reg].value = addr

  execute_inst(CORE, CALL, inst)

  state.check((reg, addr), ip = expected_ip, fp = expected_fp, sp = expected_sp)


#
# CAS
#
def __base_cas_test(state, reg1, reg2, reg3, addr, memory_value, register_value, replace, compare = None):
  from ducky.cpu.instructions import CAS

  assume((addr & 0xFFFFFFFC) == 0)
  assume(reg1 != reg2 and reg2 != reg3 and reg3 != reg1)
  assume(memory_value != replace)

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, reg3=%d, addr=0x%08X, memory_value=0x%08X, register_value=0x%08X, replace=0x%08X', state, reg1, reg2, reg3, addr, memory_value, register_value, replace)

  inst = encode_inst(CAS, {'register_n0': reg1, 'register_n1': reg2, 'register_n2': reg3})

  state.reset()
  CORE.registers.map[reg1].value = addr
  CORE.registers.map[reg2].value = register_value
  CORE.registers.map[reg3].value = replace
  CORE.mmu.memory.write_u32(addr, memory_value)

  execute_inst(CORE, CAS, inst)

  compare()

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, reg3 = REGISTER, addr = VALUE, memory_value = VALUE, register_value = VALUE, replace = VALUE)
def test_cas_success(state, reg1, reg2, reg3, addr, memory_value, register_value, replace):
  assume(memory_value == register_value)

  __base_cas_test(state, reg1, reg2, reg3, addr, memory_value, register_value, replace, compare = lambda: state.check((reg1, addr), (reg2, register_value), (reg3, replace), equal = True))

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, reg3 = REGISTER, addr = VALUE, memory_value = VALUE, register_value = VALUE, replace = VALUE)
def test_cas_failure(state, reg1, reg2, reg3, addr, memory_value, register_value, replace):
  assume(memory_value != register_value)

  __base_cas_test(state, reg1, reg2, reg3, addr, memory_value, register_value, replace, compare = lambda: state.check((reg1, addr), (reg2, memory_value), (reg3, replace), equal = False))


#
# CLI
#
@given(state = STATE)
def test_cli(state):
  assume(state.privileged is True)

  from ducky.cpu.instructions import CLI

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(CLI, {})

  state.reset()

  execute_inst(CORE, CLI, inst)

  state.check(hwint_allowed = False)

@given(state = STATE)
def test_cli_unprivileged(state):
  assume(state.privileged is False)

  from ducky.cpu.instructions import CLI

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(CLI, {})

  state.reset()

  try:
    execute_inst(CORE, CLI, inst)

  except PrivilegedInstructionError:
    pass

  else:
    assert False, 'Privileged instruction should not be allowed in non-privileged mode'

  state.check()


#
# CMP
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0, b = 0)
@example(state = STATE.example(), reg = REGISTER.example(), a = 1, b = 1)
@example(state = STATE.example(), reg = REGISTER.example(), a = 10, b = 20)
@example(state = STATE.example(), reg = 0, a = 0xFFFFFFFF, b = 0x00007FFF)
def test_cmp_immediate(state, reg, a, b):
  from ducky.cpu.instructions import CMP

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X, b=0x%08X', state, reg, a, b)

  inst = encode_inst(CMP, {'register_n0': reg, 'immediate': b})

  b_extended = sign_extend15(b)

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, CMP, inst)

  state.check((reg, a),
              equal = a == b_extended,
              zero = a == b_extended and a == 0,
              overflow = False,
              sign = i32_t(a).value < i32_t(b_extended).value)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = 0, reg2 = 0, a = 0, b = 0)
@example(state = STATE.example(), reg1 = 0, reg2 = 0, a = 1, b = 1)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = 10, b = 20)
def test_cmp_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import CMP

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X, b=0x%08X', state, reg1, reg2, a, b)

  inst = encode_inst(CMP, {'register_n0': reg1, 'register_n1': reg2})

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  execute_inst(CORE, CMP, inst)

  state.check((reg1, b if reg1 == reg2 else a), (reg2, b),
              equal = True if reg1 == reg2 else a == b,
              zero = b == 0 if reg1 == reg2 else (a == b and a == 0),
              overflow = False,
              sign = False if reg1 == reg2 else i32_t(a).value < i32_t(b).value)


#
# CMPU
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = 0, a = 0, b = 0)
@example(state = STATE.example(), reg = 0, a = 1, b = 1)
@example(state = STATE.example(), reg = 0, a = 10, b = 20)
@example(state = STATE.example(), reg = 0, a = 0xFFFFFFFF, b = 0x00007FFF)
def test_cmpu_immediate(state, reg, a, b):
  from ducky.cpu.instructions import CMPU

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X, b=0x%08X', state, reg, a, b)

  inst = encode_inst(CMPU, {'register_n0': reg, 'immediate': b})

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, CMPU, inst)

  state.check((reg, a),
              equal = a == b,
              zero = a == b and a == 0,
              overflow = False,
              sign = a < b)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), a = 0, b = 0)
@example(state = STATE.example(), reg1 = 0, reg2 = 0, a = 1, b = 1)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = 10, b = 20)
def test_cmpu_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import CMPU

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X, b=0x%08X', state, reg1, reg2, a, b)

  inst = encode_inst(CMPU, {'register_n0': reg1, 'register_n1': reg2})

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  execute_inst(CORE, CMPU, inst)

  state.check((reg1, b if reg1 == reg2 else a), (reg2, b),
              equal = True if reg1 == reg2 else a == b,
              zero = b == 0 if reg1 == reg2 else (a == b and a == 0),
              overflow = False,
              sign = False if reg1 == reg2 else a < b)


#
# DEC
#
@given(state = STATE, reg = REGISTER, a = VALUE)
@example(state = STATE.example(), reg = 0, a = 1)
@example(state = STATE.example(), reg = 0, a = 0)
def test_dec(state, reg, a):
  from ducky.cpu.instructions import DEC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X', state, reg, a)

  inst = encode_inst(DEC, {'register_n0': reg})

  value = a - 1
  expected_value = value % (2 ** 32)

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, DEC, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign = expected_value & 0x80000000 != 0)


#
# DIV
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0, b = 2)
@example(state = STATE.example(), reg = REGISTER.example(), a = 10, b = 20)
def test_div_immediate(state, reg, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import DIV

  def compute(state, reg, a, b):
    _a = i32_t(a).value
    _b = i32_t(sign_extend15(b)).value
    value = _a // _b if abs(_a) >= abs(_b) else 0
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = DIV, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = 0, b = 2)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = 10, b = 20)
def test_div_register(state, reg1, reg2, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import DIV

  def compute(state, reg1, reg2, a, b):
    _a = i32_t(a).value
    _b = i32_t(b).value
    value = 1 if reg1 == reg2 else (_a // _b if abs(_a) >= abs(_b) else 0)
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = DIV, compute = compute)

@given(state = STATE, reg = REGISTER, a = VALUE)
def test_div_zero_immediate(state, reg, a):
  from ducky.cpu.instructions import DIV

  __base_arith_by_zero_immediate(state, reg, a, inst_class = DIV)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_div_zero_register(state, reg1, reg2, a, b):
  assume(reg1 != reg2)

  from ducky.cpu.instructions import DIV

  __base_arith_by_zero_register(state, reg1, reg2, a, inst_class = DIV)


#
# HLT
#
@given(state = STATE, a = IMMEDIATE20)
def test_hlt_immediate(state, a):
  assume(state.privileged is True)
  assume(state.exit_code != a)

  from ducky.cpu.instructions import HLT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, a=%d', state, a)

  inst = encode_inst(HLT, {'immediate': a})

  expected_exit_code = sign_extend20(a)

  CORE.boot()
  state.reset()

  execute_inst(CORE, HLT, inst)

  state.check(exit_code = expected_exit_code, alive = False, running = False)

  # re-init CORE
  setup()

@given(state = STATE, reg = REGISTER, a = IMMEDIATE20)
def test_hlt_register(state, reg, a):
  assume(state.privileged is True)
  assume(state.exit_code != a)

  from ducky.cpu.instructions import HLT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=%d', state, reg, a)

  inst = encode_inst(HLT, {'register_n0': reg})

  CORE.boot()
  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, HLT, inst)

  state.check((reg, a), exit_code = a, alive = False, running = False)

  # re-init CORE
  setup()

@given(state = STATE)
def test_hlt_unprivileged(state):
  assume(state.privileged is False)

  from ducky.cpu.instructions import HLT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(HLT, {'immediate': 20})

  CORE.boot()
  state.reset()

  try:
    execute_inst(CORE, HLT, inst)

  except PrivilegedInstructionError:
    pass

  else:
    assert False, 'Privileged instruction should not be allowed in non-privileged mode'

  state.check()

  # re-init CORE
  setup()


#
# IDLE
#
@given(state = STATE)
def test_idle(state):
  from ducky.cpu.instructions import IDLE

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(IDLE, {})

  state.reset()

  execute_inst(CORE, IDLE, inst)

  state.check(idle = True)


#
# INC
#
@given(state = STATE, reg = REGISTER, a = VALUE)
@example(state = STATE.example(), reg = 0, a = 0)
@example(state = STATE.example(), reg = 0, a = 0xFFFFFFFE)
@example(state = STATE.example(), reg = 0, a = 0xFFFFFFFF)
def test_inc(state, reg, a):
  from ducky.cpu.instructions import INC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X', state, reg, a)

  inst = encode_inst(INC, {'register_n0': reg})

  value = a + 1
  expected_value = value % (2 ** 32)

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, INC, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = a == 0xFFFFFFFF, sign = expected_value & 0x80000000 != 0)


#
# INT
#
@given(state = STATE, index = IMMEDIATE20, ip = VALUE, sp = VALUE)
def test_int_immediate(state, index, ip, sp):
  assume(index < 32)

  state.sp &= 0xFFFFFFFC
  sp &= 0xFFFFFFFC

  from ducky.cpu.instructions import INT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, index=%d, ip=0x%08X, sp=0x%08X', state, index, ip, sp)

  inst = encode_inst(INT, {'immediate': index})

  state.reset()
  CORE.mmu.memory.write_u32(CORE.ivt_address + index * 8,     ip)
  CORE.mmu.memory.write_u32(CORE.ivt_address + index * 8 + 4, sp)

  execute_inst(CORE, INT, inst)

  state.check(ip = ip, fp = u32_t(sp - 16).value, sp = u32_t(sp - 16).value, privileged = True, hwint_allowed = False)

@given(state = STATE, index = IMMEDIATE20)
def test_int_immediate_out_of_range(state, index):
  assume(index >= 32)

  from ducky.cpu.instructions import INT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, index=%d', state, index)

  inst = encode_inst(INT, {'immediate': index})

  state.reset()

  try:
    execute_inst(CORE, INT, inst)

  except InvalidExceptionError as e:
    assert e.exc_index == sign_extend20(index)

  else:
    assert False, 'Instruction expected to raise error'

  state.check()

@given(state = STATE, reg = REGISTER, index = VALUE, ip = VALUE, sp = VALUE)
def test_int_register(state, reg, index, ip, sp):
  assume(index < 32)

  from ducky.cpu.instructions import INT

  state.sp &= 0xFFFFFFFC
  sp &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, r=%d, index=%d, ip=0x%08X, sp=0x%08X', state, reg, index, ip, sp)

  inst = encode_inst(INT, {'register_n0': reg})

  state.reset()
  CORE.registers.map[reg].value = index
  CORE.mmu.memory.write_u32(CORE.ivt_address + index * 8,     ip)
  CORE.mmu.memory.write_u32(CORE.ivt_address + index * 8 + 4, sp)

  execute_inst(CORE, INT, inst)

  state.check((reg, index), ip = ip, fp = u32_t(sp - 16).value, sp = u32_t(sp - 16).value, privileged = True, hwint_allowed = False)

@given(state = STATE, reg = REGISTER, index = IMMEDIATE20)
def test_int_register_out_of_range(state, reg, index):
  assume(index >= 32)

  from ducky.cpu.instructions import INT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, index=%d', state, reg, index)

  inst = encode_inst(INT, {'register_n0': reg})

  state.reset()
  CORE.registers.map[reg].value = index

  try:
    execute_inst(CORE, INT, inst)

  except InvalidExceptionError as e:
    assert e.exc_index == index

  else:
    assert False, 'Instruction expected to raise error'

  state.check((reg, index))


#
# J
#
@given(state = STATE, ip = VALUE, offset = IMMEDIATE20)
def test_j_immediate(state, ip, offset):
  from ducky.cpu.instructions import J

  ip &= 0xFFFFFFFC
  offset &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, ip=0x%08X, offset=0x%08X', state, ip, offset)

  inst = encode_inst(J, {'immediate': offset})

  expected_value = (ip + sign_extend20(offset // 4) * 4) % (2 ** 32)

  state.reset()
  CORE.registers.ip.value = ip

  execute_inst(CORE, J, inst)

  state.check(ip = expected_value)

@given(state = STATE, ip = VALUE, reg = REGISTER, addr = VALUE)
def test_j_register(state, ip, reg, addr):
  from ducky.cpu.instructions import J

  ip &= 0xFFFFFFFC

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, ip=0x%08X, reg=%d, addr=0x%08X', state, ip, reg, addr)

  inst = encode_inst(J, {'register_n0': reg})

  state.reset()
  CORE.registers.ip.value = ip
  CORE.registers.map[reg].value = addr

  execute_inst(CORE, J, inst)

  state.check((reg, addr), ip = addr)

@given(offset = IMMEDIATE20)
def test_j_unaligned(offset):
  from ducky.cpu.instructions import J

  assume(offset & 0x3 != 0)

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: offset=0x%08X' % offset)

  try:
    encode_inst(J, {'immediate': offset})

  except UnalignedJumpTargetError:
    pass

  else:
    assert False, 'Encoding expected to raise an error with un-aligned offset'


#
# LA
#
@given(state = STATE, reg = REGISTER, ip = VALUE, offset = IMMEDIATE20)
def test_la(state, reg, ip, offset):
  from ducky.cpu.instructions import LA

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, ip=0x%08X, offset=0x%08X', state, reg, ip, offset)

  inst = encode_inst(LA, {'register_n0': reg, 'immediate': offset})

  expected_value = (ip + sign_extend20(offset)) % (2 ** 32)

  state.reset()
  CORE.registers.ip.value = ip

  execute_inst(CORE, LA, inst)

  state.check((reg, expected_value), ip = ip, zero = expected_value == 0, overflow = False, sign = expected_value & 0x80000000 != 0)


#
# LB
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE8)
def test_lb(state, reg1, reg2, address, value):
  from ducky.cpu.instructions import LB

  __base_load_test(state, reg1, reg2, address, value, LB, 1)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE8, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE.example(), value = VALUE8.example(), offset = 0)
def test_lb_offset(state, reg1, reg2, address, value, offset):
  from ducky.cpu.instructions import LB

  __base_load_test(state, reg1, reg2, address, value, LB, 1, offset = offset)


#
# LI
#
@given(state = STATE, reg = REGISTER, a = IMMEDIATE20)
def test_li(state, reg, a):
  from ducky.cpu.instructions import LI

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X', state, reg, a)

  inst = encode_inst(LI, {'register_n0': reg, 'immediate': a})

  expected_value = sign_extend20(a)

  state.reset()

  execute_inst(CORE, LI, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign = expected_value & 0x80000000 != 0)


#
# LIU
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE20)
def test_liu(state, reg, a, b):
  from ducky.cpu.instructions import LIU

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X, b=0x%08X', state, reg, a, b)

  inst = encode_inst(LIU, {'register_n0': reg, 'immediate': b})

  expected_value = ((b & 0xFFFF) << 16) | (a & 0xFFFF)

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, LIU, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign = expected_value & 0x80000000 != 0)


#
# LPM
#
@given(state = STATE)
def test_lpm(state):
  assume(state.privileged is True)

  from ducky.cpu.instructions import LPM

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(LPM, {})

  state.reset()

  execute_inst(CORE, LPM, inst)

  state.check(privileged = False)

@given(state = STATE)
def test_lpm_unprivileged(state):
  assume(state.privileged is False)

  from ducky.cpu.instructions import LPM

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(LPM, {})

  state.reset()

  try:
    execute_inst(CORE, LPM, inst)

  except PrivilegedInstructionError:
    pass

  else:
    assert False, 'Access violation error expected'

  state.check()


#
# LS
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE16)
def test_ls(state, reg1, reg2, address, value):
  assume(address & 0x1 == 0)

  from ducky.cpu.instructions import LS

  __base_load_test(state, reg1, reg2, address, value, LS, 2)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE16, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE.example() & 0xFFFFFFFE, value = VALUE16.example(), offset = 0)
def test_ls_offset(state, reg1, reg2, address, value, offset):
  assume(address & 0x1 == 0)
  assume(offset & 0x1 == 0)

  from ducky.cpu.instructions import LS

  __base_load_test(state, reg1, reg2, address, value, LS, 2, offset = offset)


#
# LW
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE)
def test_lw(state, reg1, reg2, address, value):
  assume(address & 0x3 == 0)

  from ducky.cpu.instructions import LW

  __base_load_test(state, reg1, reg2, address, value, LW, 4)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE.example() & 0xFFFFFFFC, value = VALUE.example(), offset = 0)
def test_lw_offset(state, reg1, reg2, address, value, offset):
  assume(address & 0x3 == 0)
  assume(offset & 0x3 == 0)

  from ducky.cpu.instructions import LW

  __base_load_test(state, reg1, reg2, address, value, LW, 4, offset = offset)


#
# MOD
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_mod_immediate(state, reg, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import MOD

  def compute(state, reg, a, b):
    _a = i32_t(a).value
    _b = i32_t(sign_extend15(b)).value
    value = _a % _b
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = MOD, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_mod_register(state, reg1, reg2, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import MOD

  def compute(state, reg1, reg2, a, b):
    _a = i32_t(a).value
    _b = i32_t(b).value
    value = _a % _b if reg1 != reg2 else 0
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = MOD, compute = compute)

@given(state = STATE, reg = REGISTER, a = VALUE)
def test_mod_zero_immediate(state, reg, a):
  from ducky.cpu.instructions import MOD

  __base_arith_by_zero_immediate(state, reg, a, inst_class = MOD)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_mod_zero_register(state, reg1, reg2, a, b):
  assume(reg1 != reg2)

  from ducky.cpu.instructions import MOD

  __base_arith_by_zero_register(state, reg1, reg2, a, inst_class = MOD)


#
# MOV
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_mov(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import MOV

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X, b=0x%08X', state, reg1, reg2, a, b)

  inst = encode_inst(MOV, {'register_n0': reg1, 'register_n1': reg2})

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  execute_inst(CORE, MOV, inst)

  state.check((reg1, b), (reg2, b))


#
# MUL
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = REGISTER.example(), a = VALUE.example(), b = 0)
def test_mul_immediate(state, reg, a, b):
  from ducky.cpu.instructions import MUL

  def compute(state, reg, a, b):
    value = i32_t(a).value * i32_t(sign_extend15(b)).value
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = MUL, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = VALUE.example(), b = 0)
def test_mul_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import MUL

  def compute(state, reg1, reg2, a, b):
    value = i32_t(b).value * i32_t(b).value if reg1 == reg2 else i32_t(a).value * i32_t(b).value
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = MUL, compute = compute)


#
# NOP
#
@given(state = STATE)
def test_nop(state):
  from ducky.cpu.instructions import NOP

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(NOP, {})

  state.reset()

  execute_inst(CORE, NOP, inst)

  state.check()


#
# NOT
#
@given(state = STATE, reg = REGISTER, a = VALUE)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0xFFF0FFF0)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0x00000000)
@example(state = STATE.example(), reg = REGISTER.example(), a = 0xFFFFFFFF)
def test_not(state, reg, a):
  from ducky.cpu.instructions import NOT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg=%d, a=0x%08X', state, reg, a)

  inst = encode_inst(NOT, {'register_n0': reg})

  value = ~a
  expected_value = u32_t(value).value

  state.reset()
  CORE.registers.map[reg].value = a

  execute_inst(CORE, NOT, inst)

  state.check((reg, expected_value), zero = expected_value == 0, overflow = False, sign  = expected_value & 0x80000000 != 0)


#
# OR
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_or_immediate(state, reg, a, b):
  from ducky.cpu.instructions import OR

  def compute(state, reg, a, b):
    value = a | sign_extend15(b)
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = OR, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_or_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import OR

  def compute(state, reg1, reg2, a, b):
    value = b if reg1 == reg2 else a | b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = OR, compute = compute)


#
# RET
#
@given(state = STATE, fp = VALUE, ip = VALUE)
def test_ret(state, fp, ip):
  state.sp &= 0xFFFFFFFC

  assume(state.fp != fp)
  assume(state.ip != ip)

  from ducky.cpu.instructions import RET

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, fp=0x%08X, ip=0x%08X', state, fp, ip)

  inst = encode_inst(RET, {})

  state.reset()

  CORE.mmu.memory.write_u32(state.sp, fp)
  state.sp = (state.sp + 4) % (2 ** 32)
  CORE.mmu.memory.write_u32(state.sp, ip)
  state.sp = (state.sp + 4) % (2 ** 32)

  execute_inst(CORE, RET, inst)

  state.check(fp = fp, ip = ip)


#
# RETINT
#
@given(state = STATE, fp = VALUE, ip = VALUE, user_flags = VALUE, sp = VALUE)
def test_retint(state, fp, ip, user_flags, sp):
  assume(state.privileged is True)

  state.sp &= 0xFFFFFFFC

  assume(state.fp != fp)
  assume(state.ip != ip)
  assume(state.sp != sp)

  from ducky.cpu.instructions import RETINT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, fp=0x%08X, ip=0x%08X, user_flags=%r, sp=0x%08X', state, fp, ip, user_flags, sp)

  inst = encode_inst(RETINT, {})

  state.reset()

  CORE.instruction_set_stack.append(DuckyInstructionSet)

  CORE.mmu.memory.write_u32(state.sp, fp)
  state.sp = (state.sp + 4) % (2 ** 32)
  CORE.mmu.memory.write_u32(state.sp, ip)
  state.sp = (state.sp + 4) % (2 ** 32)
  CORE.mmu.memory.write_u32(state.sp, user_flags)
  state.sp = (state.sp + 4) % (2 ** 32)
  CORE.mmu.memory.write_u32(state.sp, sp)
  state.sp = (state.sp + 4) % (2 ** 32)

  execute_inst(CORE, RETINT, inst)

  state.flags_from_int(user_flags)
  state.check(fp = fp, ip = ip, sp = sp)
  assert len(CORE.instruction_set_stack) == 0, 'Unexpected instruction set stack content'

@given(state = STATE)
def test_retint_unprivileged(state):
  assume(state.privileged is False)

  from ducky.cpu.instructions import RETINT

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(RETINT, {})

  state.reset()

  try:
    execute_inst(CORE, RETINT, inst)

  except PrivilegedInstructionError:
    pass

  else:
    assert False, 'Privileged instruction should not be allowed in non-privileged mode'

  state.check()


#
# RST
#
@given(state = STATE)
def test_rst(state):
  assume(state.privileged is True)

  from ducky.cpu.instructions import RST

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(RST, {})

  state.reset()

  execute_inst(CORE, RST, inst)

  state.check(*[(i, 0x00000000) for i, _ in enumerate(REGISTER_NAMES) if i != ducky.cpu.registers.Registers.CNT], hwint_allowed = False, equal = False, zero = False, overflow = False, sign = False)


#
# SELE
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_sele_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELE

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELE, cond = lambda f: f.equal is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_sele_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELE

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELE, cond = lambda f: f.equal is True)


#
# SELG
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selg_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELG

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELG, cond = lambda f: f.sign is False and f.equal is False)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selg_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELG

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELG, cond = lambda f: f.sign is False and f.equal is False)


#
# SELGE
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selge_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELGE

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELGE, cond = lambda f: f.sign is False or f.equal is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selge_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELGE

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELGE, cond = lambda f: f.sign is False or f.equal is True)


#
# SELLE
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selle_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELLE

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELLE, cond = lambda f: f.sign is True or f.equal is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selle_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELLE

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELLE, cond = lambda f: f.sign is True or f.equal is True)


#
# SELNE
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selne_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELNE

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELNE, cond = lambda f: f.equal is False)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selne_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELNE

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELNE, cond = lambda f: f.equal is False)


#
# SELNO
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selno_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELNO

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELNO, cond = lambda f: f.overflow is False)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selno_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELNO

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELNO, cond = lambda f: f.overflow is False)


#
# SELNS
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selns_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELNS

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELNS, cond = lambda f: f.sign is False)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selns_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELNS

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELNS, cond = lambda f: f.sign is False)


#
# SELNZ
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selnz_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELNZ

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELNZ, cond = lambda f: f.zero is False)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selnz_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELNZ

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELNZ, cond = lambda f: f.zero is False)


#
# SELO
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selo_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELO

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELO, cond = lambda f: f.overflow is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selo_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELO

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELO, cond = lambda f: f.overflow is True)


#
# SELS
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_sels_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELS

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELS, cond = lambda f: f.sign is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_sels_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELS

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELS, cond = lambda f: f.sign is True)


#
# SELZ
#
@given(state = STATE, reg = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selz_immediate(state, reg, tv, fv):
  from ducky.cpu.instructions import SELZ

  __base_select_test_immediate(state, reg, tv, fv, inst_class = SELZ, cond = lambda f: f.zero is True)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, tv = VALUE, fv = IMMEDIATE11)
def test_selz_register(state, reg1, reg2, tv, fv):
  from ducky.cpu.instructions import SELZ

  __base_select_test_register(state, reg1, reg2, tv, fv, inst_class = SELZ, cond = lambda f: f.zero is True)


#
# SETE
#
@given(state = STATE, reg = REGISTER)
def test_sete(state, reg):
  from ducky.cpu.instructions import SETE

  __base_setting_test(state, reg, inst_class = SETE, cond = lambda f: f.equal is True)


#
# SETG
#
@given(state = STATE, reg = REGISTER)
def test_setg(state, reg):
  from ducky.cpu.instructions import SETG

  __base_setting_test(state, reg, inst_class = SETG, cond = lambda f: f.sign is False and f.equal is False)


#
# SETGE
#
@given(state = STATE, reg = REGISTER)
def test_setge(state, reg):
  from ducky.cpu.instructions import SETGE

  __base_setting_test(state, reg, inst_class = SETGE, cond = lambda f: f.sign is False or f.equal is True)


#
# SETL
#
@given(state = STATE, reg = REGISTER)
def test_setl(state, reg):
  from ducky.cpu.instructions import SETL

  __base_setting_test(state, reg, inst_class = SETL, cond = lambda f: f.sign is True and f.equal is False)


#
# SETLE
#
@given(state = STATE, reg = REGISTER)
def test_setgl(state, reg):
  from ducky.cpu.instructions import SETLE

  __base_setting_test(state, reg, inst_class = SETLE, cond = lambda f: f.sign is True or f.equal is True)


#
# SETNE
#
@given(state = STATE, reg = REGISTER)
def test_setne(state, reg):
  from ducky.cpu.instructions import SETNE

  __base_setting_test(state, reg, inst_class = SETNE, cond = lambda f: f.equal is False)


#
# SETNO
#
@given(state = STATE, reg = REGISTER)
def test_setno(state, reg):
  from ducky.cpu.instructions import SETNO

  __base_setting_test(state, reg, inst_class = SETNO, cond = lambda f: f.overflow is False)


#
# SETNS
#
@given(state = STATE, reg = REGISTER)
def test_setns(state, reg):
  from ducky.cpu.instructions import SETNS

  __base_setting_test(state, reg, inst_class = SETNS, cond = lambda f: f.sign is False)


#
# SETNZ
#
@given(state = STATE, reg = REGISTER)
def test_setnz(state, reg):
  from ducky.cpu.instructions import SETNZ

  __base_setting_test(state, reg, inst_class = SETNZ, cond = lambda f: f.zero is False)


#
# SETO
#
@given(state = STATE, reg = REGISTER)
def test_seto(state, reg):
  from ducky.cpu.instructions import SETO

  __base_setting_test(state, reg, inst_class = SETO, cond = lambda f: f.overflow is True)


#
# SETS
#
@given(state = STATE, reg = REGISTER)
def test_sets(state, reg):
  from ducky.cpu.instructions import SETS

  __base_setting_test(state, reg, inst_class = SETS, cond = lambda f: f.sign is True)


#
# SETZ
#
@given(state = STATE, reg = REGISTER)
def test_setz(state, reg):
  from ducky.cpu.instructions import SETZ

  __base_setting_test(state, reg, inst_class = SETZ, cond = lambda f: f.zero is True)


#
# SHIFTL
#
if PYPY:
  cap_shift = partial(min, 32)

else:
  def cap_shift(n):
    return n

@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = 0, a = 0x01000000, b = 8)
def test_shiftl_immediate(state, reg, a, b):
  from ducky.cpu.instructions import SHIFTL

  def compute(state, reg, a, b):
    value = a << cap_shift(sign_extend15(b))
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = SHIFTL, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = 0, reg2 = 1, a = 0x01000000, b = 8)
def test_shiftl_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import SHIFTL

  def compute(state, reg1, reg2, a, b):
    value = b << cap_shift(b) if reg1 == reg2 else a << cap_shift(b)
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = SHIFTL, compute = compute)


#
# SHIFTR
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_shiftr_immediate(state, reg, a, b):
  from ducky.cpu.instructions import SHIFTR

  def compute(state, reg, a, b):
    value = a >> cap_shift(sign_extend15(b))
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = SHIFTR, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_shiftr_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import SHIFTR

  def compute(state, reg1, reg2, a, b):
    value = b >> cap_shift(b) if reg1 == reg2 else a >> cap_shift(b)
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = SHIFTR, compute = compute)


#
# STB
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE8)
def test_stb(state, reg1, reg2, address, value):
  from ducky.cpu.instructions import STB

  if reg1 == reg2:
    value = address & 0xFF

  __base_store_test(state, reg1, reg2, address, value, STB, 1)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE8, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE8.example(), value = VALUE.example(), offset = 0)
def test_stb_offset(state, reg1, reg2, address, value, offset):
  from ducky.cpu.instructions import STB

  if reg1 == reg2:
    value = address & 0xFF

  __base_store_test(state, reg1, reg2, address, value, STB, 1, offset = offset)


#
# STS
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE16)
def test_sts(state, reg1, reg2, address, value):
  assume(address & 0x1 == 0)

  from ducky.cpu.instructions import STS

  if reg1 == reg2:
    value = address & 0xFFFF

  __base_store_test(state, reg1, reg2, address, value, STS, 2)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE16, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE.example() & 0xFFFFFFFE, value = VALUE16.example(), offset = 0)
def test_sts_offset(state, reg1, reg2, address, value, offset):
  assume(address & 0x1 == 0)
  assume(offset & 0x1 == 0)

  from ducky.cpu.instructions import STS

  if reg1 == reg2:
    value = address & 0xFFFF

  __base_store_test(state, reg1, reg2, address, value, STS, 2, offset = offset)


#
# STW
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE)
def test_stw(state, reg1, reg2, address, value):
  assume(address & 0x3 == 0)

  from ducky.cpu.instructions import STW

  if reg1 == reg2:
    value = address

  __base_store_test(state, reg1, reg2, address, value, STW, 4)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, address = VALUE, value = VALUE, offset = IMMEDIATE15)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), address = VALUE.example() & 0xFFFFFFFC, value = VALUE.example(), offset = 0)
def test_stw_offset(state, reg1, reg2, address, value, offset):
  assume(address & 0x3 == 0)
  assume(offset & 0x3 == 0)

  from ducky.cpu.instructions import STW

  if reg1 == reg2:
    value = address

  __base_store_test(state, reg1, reg2, address, value, STW, 4, offset = offset)


#
# STI
#
@given(state = STATE)
def test_sti(state):
  assume(state.privileged is True)

  from ducky.cpu.instructions import STI

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(STI, {})

  state.reset()

  execute_inst(CORE, STI, inst)

  state.check(hwint_allowed = True)

@given(state = STATE)
def test_sti_unprivileged(state):
  assume(state.privileged is False)

  from ducky.cpu.instructions import STI

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r', state)

  inst = encode_inst(STI, {})

  state.reset()

  try:
    execute_inst(CORE, STI, inst)

  except PrivilegedInstructionError:
    pass

  else:
    assert False, 'Privileged instruction should not be allowed in non-privileged mode'

  state.check()


#
# SUB
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_sub_immediate(state, reg, a, b):
  from ducky.cpu.instructions import SUB

  def compute(state, reg, a, b):
    value = a - sign_extend15(b)
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = SUB, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_sub_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import SUB

  def compute(state, reg1, reg2, a, b):
    value = 0 if reg1 == reg2 else a - b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = SUB, compute = compute)


#
# SWP
#
@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_swap(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import SWP

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, reg1=%d, reg2=%d, a=0x%08X, b=0x%08X' % (state, reg1, reg2, a, b))

  inst = encode_inst(SWP, {'register_n0': reg1, 'register_n1': reg2})

  state.reset()
  CORE.registers.map[reg1].value = a
  CORE.registers.map[reg2].value = b

  execute_inst(CORE, SWP, inst)

  state.check((reg1, b), (reg2, a if reg1 != reg2 else b))


#
# UDIV
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
def test_udiv_immediate(state, reg, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import UDIV

  def compute(state, reg, a, b):
    _a = u32_t(a).value
    _b = u32_t(sign_extend15(b)).value
    value = _a // _b
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = UDIV, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_udiv_register(state, reg1, reg2, a, b):
  assume(b != 0)

  from ducky.cpu.instructions import UDIV

  def compute(state, reg1, reg2, a, b):
    _a = u32_t(a).value
    _b = u32_t(b).value
    value = 1 if reg1 == reg2 else _a // _b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = UDIV, compute = compute)

@given(state = STATE, reg = REGISTER, a = VALUE)
def test_udiv_zero_immediate(state, reg, a):
  from ducky.cpu.instructions import UDIV

  __base_arith_by_zero_immediate(state, reg, a, inst_class = UDIV)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
def test_udiv_zero_register(state, reg1, reg2, a, b):
  assume(reg1 != reg2)

  from ducky.cpu.instructions import UDIV

  __base_arith_by_zero_register(state, reg1, reg2, a, inst_class = UDIV)


#
# XOR
#
@given(state = STATE, reg = REGISTER, a = VALUE, b = IMMEDIATE15)
@example(state = STATE.example(), reg = REGISTER.example(), a = 10, b = 10)
def test_xor_immediate(state, reg, a, b):
  from ducky.cpu.instructions import XOR

  def compute(state, reg, a, b):
    value = a ^ sign_extend15(b)
    return value, u32_t(value).value

  __base_arith_test_immediate(state, reg, a, b, inst_class = XOR, compute = compute)

@given(state = STATE, reg1 = REGISTER, reg2 = REGISTER, a = VALUE, b = VALUE)
@example(state = STATE.example(), reg1 = REGISTER.example(), reg2 = REGISTER.example(), a = 10, b = 10)
@example(state = STATE.example(), reg1 = 0, reg2 = 0, a = 10, b = 10)
def test_xor_register(state, reg1, reg2, a, b):
  from ducky.cpu.instructions import XOR

  def compute(state, reg1, reg2, a, b):
    value = 0 if reg1 == reg2 else a ^ b
    return value, u32_t(value).value

  __base_arith_test_register(state, reg1, reg2, a, b, inst_class = XOR, compute = compute)
