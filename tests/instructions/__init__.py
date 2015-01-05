import functools
import unittest

from tests import run_machine, assert_registers, assert_flags

common_machine_run = functools.partial(run_machine, cpus = 1, cores = 1, irq_routines = 'instructions/interrupts-basic.bin')

class Tests(unittest.TestCase):
  def test_nop(self):
    state = common_machine_run('main:\nnop\nint 0')
    assert_registers(state.core_states[0])
    assert_flags(state.core_states[0])

  def test_inc(self):
    state = common_machine_run('main:\nli r0, 0\ninc r0\nint 0')
    assert_registers(state.core_states[0], r0 = 1)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 1\ninc r0\nint 0')
    assert_registers(state.core_states[0], r0 = 2)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFFE\ninc r0\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFF)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFFF\ninc r0\nint 0')
    assert_registers(state.core_states[0], r0 = 0)
    assert_flags(state.core_states[0], z = 1)

  def test_dec(self):
    state = common_machine_run('main:\nli r0, 1\ndec r0\nint 0')
    assert_registers(state.core_states[0])
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 0\ndec r0\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFF)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 2\ndec r0\nint 0')
    assert_registers(state.core_states[0], r0 = 1)
    assert_flags(state.core_states[0])

  def test_add(self):
    state = common_machine_run('main:\nli r0, 5\nli r1, 10\nadd r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 15, r1 = 10)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFFE\nli r1, 2\nadd r0, r1\nint 0')
    assert_registers(state.core_states[0], r1 = 2)
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 0xFFFE\nli r1, 4\nadd r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 2, r1 = 4)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 5\nadd r0, 10\nint 0')
    assert_registers(state.core_states[0], r0 = 15)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFFE\nadd r0, 2\nint 0')
    assert_registers(state.core_states[0])
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 0xFFFE\nadd r0, 4\nint 0')
    assert_registers(state.core_states[0], r0 = 2)
    assert_flags(state.core_states[0])

  def test_sub(self):
    state = common_machine_run('main:\nli r0, 15\nli r1, 5\nsub r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 10, r1 = 5)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 2\nli r1, 2\nsub r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 0, r1 = 2)
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 2\nli r1, 4\nsub r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFE, r1 = 4)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 15\nsub r0, 5\nint 0')
    assert_registers(state.core_states[0], r0 = 10)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 2\nsub r0, 2\nint 0')
    assert_registers(state.core_states[0])
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 2\nsub r0, 4\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFE)
    assert_flags(state.core_states[0])

  def test_and(self):
    state = common_machine_run('main:\nli r0, 0xFFFF\nli r1, 0x0008\nand r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 0x0008, r1 = 0x0008)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0x0008\nli r1, 0x0004\nand r0, r1\nint 0')
    assert_registers(state.core_states[0], r1 = 0x0004)
    assert_flags(state.core_states[0], z = 1)

    state = common_machine_run('main:\nli r0, 0xFFFF\nand r0, 0x0008\nint 0')
    assert_registers(state.core_states[0], r0 = 0x0008)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0x0008\nand r0, 0x0004\nint 0')
    assert_registers(state.core_states[0])
    assert_flags(state.core_states[0], z = 1)

  def test_or(self):
    state = common_machine_run('main:\nli r0, 0xFFF0\nli r1, 0x000F\nor r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFF, r1 = 0x000F)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFF0\nli r1, 0x00F0\nor r0, r1\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFF0, r1 = 0x00F0)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFF0\nor r0, 0x000F\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFFF)
    assert_flags(state.core_states[0])

    state = common_machine_run('main:\nli r0, 0xFFF0\nor r0, 0x00F0\nint 0')
    assert_registers(state.core_states[0], r0 = 0xFFF0)
    assert_flags(state.core_states[0])

