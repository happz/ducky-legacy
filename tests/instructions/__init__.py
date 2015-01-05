import functools
import unittest

from tests import run_machine, assert_registers, assert_flags

class Tests(unittest.TestCase):
  def common_case(self, code, **kwargs):
    state = run_machine(code, cpus = 1, cores = 1, irq_routines = 'instructions/interrupts-basic.bin')
    assert_registers(state.core_states[0], **kwargs)
    assert_flags(state.core_states[0], **kwargs)

  def test_nop(self):
    self.common_case('main:\nnop\nint 0')

  def test_inc(self):
    self.common_case('main:\nli r0, 0\ninc r0\nint 0', r0 = 1)
    self.common_case('main:\nli r0, 1\ninc r0\nint 0', r0 = 2)
    self.common_case('main:\nli r0, 0xFFFE\ninc r0\nint 0', r0 = 0xFFFF)
    self.common_case('main:\nli r0, 0xFFFF\ninc r0\nint 0', r0 = 0, z = 1)

  def test_dec(self):
    self.common_case('main:\nli r0, 1\ndec r0\nint 0', z = 1)
    self.common_case('main:\nli r0, 0\ndec r0\nint 0', r0 = 0xFFFF)
    self.common_case('main:\nli r0, 2\ndec r0\nint 0', r0 = 1)

  def test_add(self):
    self.common_case('main:\nli r0, 5\nli r1, 10\nadd r0, r1\nint 0', r0 = 15, r1 = 10)
    self.common_case('main:\nli r0, 0xFFFE\nli r1, 2\nadd r0, r1\nint 0', r1 = 2, z = 1)
    self.common_case('main:\nli r0, 0xFFFE\nli r1, 4\nadd r0, r1\nint 0', r0 = 2, r1 = 4)
    self.common_case('main:\nli r0, 5\nadd r0, 10\nint 0', r0 = 15)
    self.common_case('main:\nli r0, 0xFFFE\nadd r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 0xFFFE\nadd r0, 4\nint 0', r0 = 2)

  def test_sub(self):
    self.common_case('main:\nli r0, 15\nli r1, 5\nsub r0, r1\nint 0', r0 = 10, r1 = 5)
    self.common_case('main:\nli r0, 2\nli r1, 2\nsub r0, r1\nint 0', r0 = 0, r1 = 2, z = 1)
    self.common_case('main:\nli r0, 2\nli r1, 4\nsub r0, r1\nint 0', r0 = 0xFFFE, r1 = 4)
    self.common_case('main:\nli r0, 15\nsub r0, 5\nint 0', r0 = 10)
    self.common_case('main:\nli r0, 2\nsub r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 2\nsub r0, 4\nint 0', r0 = 0xFFFE)

  def test_and(self):
    self.common_case('main:\nli r0, 0xFFFF\nli r1, 0x0008\nand r0, r1\nint 0', r0 = 0x0008, r1 = 0x0008)
    self.common_case('main:\nli r0, 0x0008\nli r1, 0x0004\nand r0, r1\nint 0', r1 = 0x0004, z = 1)
    self.common_case('main:\nli r0, 0xFFFF\nand r0, 0x0008\nint 0', r0 = 0x0008)
    self.common_case('main:\nli r0, 0x0008\nand r0, 0x0004\nint 0', z = 1)

  def test_or(self):
    self.common_case('main:\nli r0, 0xFFF0\nli r1, 0x000F\nor r0, r1\nint 0', r0 = 0xFFFF, r1 = 0x000F)
    self.common_case('main:\nli r0, 0xFFF0\nli r1, 0x00F0\nor r0, r1\nint 0', r0 = 0xFFF0, r1 = 0x00F0)
    self.common_case('main:\nli r0, 0xFFF0\nor r0, 0x000F\nint 0', r0 = 0xFFFF)
    self.common_case('main:\nli r0, 0xFFF0\nor r0, 0x00F0\nint 0', r0 = 0xFFF0)

  def test_xor(self):
    self.common_case('main:\nli r0, 0x00F0\nli r1, 0x0F0F\nxor r0, r1\nint 0', r0 = 0x0FFF, r1 = 0x0F0F)
    self.common_case('main:\nli r0, 0x00F0\nxor r0, 0x0F0F\nint 0', r0 = 0x0FFF)
    self.common_case('main:\nli r0, 0x00F0\nli r1, 0x0FF0\nxor r0, r1\nint 0', r0 = 0x0F00, r1 = 0x0FF0)
    self.common_case('main:\nli r0, 0x00F0\nxor r0, 0x0FF0\nint 0', r0 = 0x0F00)
    self.common_case('main:\nli r0, 0x00F0\nxor r0, r0\nint 0', z = 1)

  def test_not(self):
    self.common_case('main:\nli r0, 0xFFF0\nnot r0\nint 0', r0 = 0x000F)
    self.common_case('main:\nli r0, 0x0\nnot r0\nint 0', r0 = 0xFFFF)
    self.common_case('main:\nli r0, 0xFFFF\nnot r0\nint 0', z = 1)

  def test_shiftl(self):
    self.common_case('main:\nli r0, 1\nshiftl r0, 1\nint 0', r0 = 2)
    self.common_case('main:\nli r0, 1\nshiftl r0, 4\nint 0', r0 = 16)
    self.common_case('main:\nli r0, 0x8000\nshiftl r0, 1\nint 0', z = 1)
    self.common_case('main:\nli r0, 0\nshiftl r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 0x00F0\nshiftl r0, 4\nint 0', r0 = 0x0F00)

  def test_shiftr(self):
    self.common_case('main:\nli r0, 2\nshiftr r0, 1\nint 0', r0 = 1)
    self.common_case('main:\nli r0, 16\nshiftr r0, 4\nint 0', r0 = 1)
    self.common_case('main:\nli r0, 0x0002\nshiftr r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 0\nshiftr r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 0x00F0\nshiftr r0, 4\nint 0', r0 = 0x000F)

  def test_mov(self):
    self.common_case('main:\nli r0, 10\nli r1, 20\nmov r0, r1\nint 0', r0 = 20, r1 = 20)
    self.common_case('main:\nli r0, 10\nli r1, 0\nmov r0, r1\nint 0', z = 1)

  def test_swap(self):
    self.common_case('main:\nli r0, 10\nli r1, 20\nswp r0, r1\nint 0', r0 = 20, r1 = 10)

