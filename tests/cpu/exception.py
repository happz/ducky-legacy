from six.moves import range

import ducky.config
from ducky.cpu import InterruptVector
from ducky.cpu.instructions import encoding_to_u32
from ducky.errors import ExceptionList
from ducky.mm import PAGE_SIZE, DEFAULT_MEMORY_SIZE, WORD_SIZE, UINT32_FMT

from hypothesis import given, assume
from hypothesis.strategies import integers, composite, lists

from .. import common_run_machine, LOGGER
from ..instructions import encode_inst

def create_machine(**kwargs):
  machine_config = ducky.config.MachineConfig()

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False], **kwargs)

  return M

EXC_INDEX = integers(min_value = 0, max_value = ExceptionList.COUNT - 1)

@composite
def __VALUE_W(draw, base = integers(min_value = 0, max_value = DEFAULT_MEMORY_SIZE // WORD_SIZE)):
  return draw(base) * WORD_SIZE

VALUE_W = __VALUE_W()

@composite
def __VALUE_PAGE(draw, base = integers(min_value = 0, max_value = DEFAULT_MEMORY_SIZE // PAGE_SIZE)):
  return draw(base) * PAGE_SIZE

VALUE_PAGE = __VALUE_PAGE()

from ..instructions import setup, STATE

CORE = None

def __base_exception_test_test(state, core, exc_routine, exc_stack, exc_args, *args, **kwargs):
  state.check(ip = exc_routine,
              fp = exc_stack - 4 * WORD_SIZE,
              sp = exc_stack - (4 + len(exc_args)) * WORD_SIZE,
              privileged = True,
              hwint_allowed = False,
              *args,
              **kwargs)

  for addr, expected_value in zip(range(state.sp, state.sp + len(exc_args) * WORD_SIZE, WORD_SIZE), reversed(exc_args)):
    actual_value = core.cpu.machine.memory.read_u32(addr)

    if actual_value == expected_value:
      LOGGER.debug('exception argument match: %s=%s', UINT32_FMT(addr), UINT32_FMT(expected_value))
      continue

    LOGGER.error('Exception argument mismatch: %s expected at %s, %s found', UINT32_FMT(expected_value), UINT32_FMT(addr), UINT32_FMT(actual_value))
    assert False

def __base_exception_test(state, index, ivt, stack, exc_stack, exc_routine, trap, trigger, test):
  assume(ivt != stack != exc_stack != exc_routine != trap)
  assume(stack >= PAGE_SIZE)
  assume(exc_stack >= PAGE_SIZE)
  assume(exc_stack != ivt + PAGE_SIZE)  # don't let exception stack overwrite IVT
  assume(not (ivt <= state.ip < ivt + PAGE_SIZE))  # lets pretend noone could put IP inside IVT
  assume(state.ip & 0x03 == 0)  # IP must be aligned

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: state=%r, index=%d, ivt=%s, stack=%s, exc_stack=%s, exc_routine=%s, trap=%s', state, index, UINT32_FMT(ivt), UINT32_FMT(stack), UINT32_FMT(exc_stack), UINT32_FMT(exc_routine), UINT32_FMT(trap))

  setup()
  from ..instructions import CORE
  M = CORE.cpu.machine

  state.reset()

  LOGGER.debug('filling IVT with trap pattern')
  for i in range(ivt, ivt + PAGE_SIZE, InterruptVector.SIZE):
    M.memory.write_u32(i, trap)
    M.memory.write_u32(i + WORD_SIZE, trap)

  LOGGER.debug('writing IVT table entry for index')
  M.memory.write_u32(ivt + InterruptVector.SIZE * index, exc_routine)
  M.memory.write_u32(ivt + InterruptVector.SIZE * index + WORD_SIZE, exc_stack)

  CORE.ivt_address = ivt
  CORE.registers.sp.value = stack

  trigger(state, CORE)
  test(state, CORE)

@given(state = STATE, index = EXC_INDEX, ivt = VALUE_PAGE, stack = VALUE_PAGE, exc_stack = VALUE_PAGE, exc_routine = VALUE_PAGE, exc_args = lists(integers(min_value = 0, max_value = 0xFFFFFFFF), min_size = 1), trap = VALUE_PAGE)
def test_sanity_enter(state, index, ivt, stack, exc_stack, exc_routine, exc_args, trap):
  def trigger(state, core):
    core._handle_exception(None, index, *exc_args)

  def test(state, core):
    __base_exception_test_test(state, core, exc_routine, exc_stack, exc_args)

  __base_exception_test(state, index, ivt, stack, exc_stack, exc_routine, trap, trigger, test)


@given(state = STATE, ivt = VALUE_PAGE, stack = VALUE_PAGE, exc_stack = VALUE_PAGE, exc_routine = VALUE_PAGE, trap = VALUE_PAGE)
def test_divide_by_zero(state, ivt, stack, exc_stack, exc_routine, trap):
  userspace_ip = state.ip

  def trigger(state, core):
    from ducky.cpu.instructions import DIV

    inst = encode_inst(DIV, {'register_n0': 5, 'immediate': 0})
    inst = encoding_to_u32(inst)

    state.r5 = core.registers.r5.value = 10
    core.cpu.machine.memory.write_u32(state.ip, inst)

    core.step()

  def test(state, core):
    __base_exception_test_test(state, core, exc_routine, exc_stack, [userspace_ip])

  __base_exception_test(state, ExceptionList.DivideByZero, ivt, stack, exc_stack, exc_routine, trap, trigger, test)
