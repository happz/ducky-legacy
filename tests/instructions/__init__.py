import functools
import types
import unittest

from util import str2int
from mm import addr_to_page, addr_to_offset, buff_to_uint16, ADDR_FMT, UINT8_FMT, UINT16_FMT

from tests import run_machine, assert_registers, assert_flags, assert_mm

class Tests(unittest.TestCase):
  def common_case(self, code, **kwargs):
    if type(code) == types.ListType:
      code = '\n'.join(code)

    state = run_machine(code, cpus = 1, cores = 1, irq_routines = 'tests/instructions/interrupts-basic.bin')
    assert_registers(state.core_states[0], **kwargs)
    assert_flags(state.core_states[0], **kwargs)

    if 'mm' in kwargs:
      assert_mm(state, **kwargs['mm'])

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
    self.common_case('main:\nli r0, 0xFFFE\nli r1, 2\nadd r0, r1\nint 0', r1 = 2, o = 1, z = 1)
    self.common_case('main:\nli r0, 0xFFFE\nli r1, 4\nadd r0, r1\nint 0', r0 = 2, r1 = 4, o = 1)
    self.common_case('main:\nli r0, 5\nadd r0, 10\nint 0', r0 = 15)
    self.common_case('main:\nli r0, 0xFFFE\nadd r0, 2\nint 0', o = 1, z = 1)
    self.common_case('main:\nli r0, 0xFFFE\nadd r0, 4\nint 0', r0 = 2, o = 1)

  def test_sub(self):
    self.common_case('main:\nli r0, 15\nli r1, 5\nsub r0, r1\nint 0', r0 = 10, r1 = 5)
    self.common_case('main:\nli r0, 2\nli r1, 2\nsub r0, r1\nint 0', r0 = 0, r1 = 2, z = 1)
    self.common_case('main:\nli r0, 2\nli r1, 4\nsub r0, r1\nint 0', r0 = 0xFFFE, r1 = 4, s = 1)
    self.common_case('main:\nli r0, 15\nsub r0, 5\nint 0', r0 = 10)
    self.common_case('main:\nli r0, 2\nsub r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 2\nsub r0, 4\nint 0', r0 = 0xFFFE, s = 1)

  def test_mul(self):
    self.common_case('main:\nli r0, 5\nli r1, 3\nmul r0, r1\nint 0', r0 = 15, r1 = 3)
    self.common_case('main:\nli r0, 5\nmul r0, 3\nint 0', r0 = 15)
    self.common_case('main:\nli r0, 5\nli r1, 0\nmul r0, r1\nint 0', z = 1)
    self.common_case('main:\nli r0, 5\nmul r0, 0\nint 0', z = 1)

  def test_div(self):
    self.common_case('main:\nli r0, 10\nli r1, 2\ndiv r0, r1\nint 0', r0 = 5, r1 = 2)
    self.common_case('main:\nli r0, 10\ndiv r0, 2\nint 0', r0 = 5)
    self.common_case('main:\nli r0, 0\nli r1, 2\ndiv r0, r1\nint 0', r1 = 2, z = 1)
    self.common_case('main:\nli r0, 0\ndiv r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 10\nli r1, 20\ndiv r0, r1\nint 0', r1 = 20, z = 1)
    self.common_case('main:\nli r0, 10\ndiv r0, 20\nint 0', z = 1)
    # TODO: division by zeor

  def test_mod(self):
    #self.common_case('main:\nli r0, 10\nli r1, 0\nmod r0, r1\nint 0', r0 = 10)
    #self.common_case('main:\nli r0, 10\nmod r0, 0\nint 0', r0 = 10)
    self.common_case('main:\nli r0, 10\nli r1, 1\nmod r0, r1\nint 0', r1 = 1, z = 1)
    self.common_case('main:\nli r0, 10\nmod r0, 1\nint 0', z = 1)
    self.common_case('main:\nli r0, 10\nli r1, 2\nmod r0, r1\nint 0', r1 = 2, z = 1)
    self.common_case('main:\nli r0, 10\nmod r0, 2\nint 0', z = 1)
    self.common_case('main:\nli r0, 10\nli r1, 3\nmod r0, r1\nint 0', r0 = 1, r1 = 3)
    self.common_case('main:\nli r0, 10\nmod r0, 3\nint 0', r0 = 1)
    self.common_case('main:\nli r0, 10\nli r1, 4\nmod r0, r1\nint 0', r0 = 2, r1 = 4)
    self.common_case('main:\nli r0, 10\nmod r0, 4\nint 0', r0 = 2)

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

  def test_cmp(self):
    self.common_case(['main:', 'li r0, 0', 'cmp r0, r0', 'int 0'], e = 1, z = 1)
    self.common_case(['main:', 'li r0, 0', 'cmp r0, 0', 'int 0'], e = 1, z = 1)
    self.common_case(['main:', 'li r0, 1', 'cmp r0, r0', 'int 0'], r0 = 1, e = 1)
    self.common_case(['main:', 'li r0, 1', 'cmp r0, 1', 'int 0'], r0 = 1, e = 1)
    self.common_case(['main:', 'li r0, 1', 'li r1, 0', 'cmp r0, r1', 'int 0'], r0 = 1)
    self.common_case(['main:', 'li r0, 1', 'cmp r0, 0', 'int 0'], r0 = 1)
    self.common_case(['main:', 'li r0, 10', 'li r1, 20', 'cmp r0, r1', 'int 0'], r0 = 10, r1 = 20, s = 1)
    self.common_case(['main:', 'li r0, 10', 'cmp r0, 20', 'int 0'], r0 = 10, s = 1)
    self.common_case(['main:', 'li r0, 20', 'li r1, 10', 'cmp r0, r1', 'int 0'], r0 = 20, r1 = 10)
    self.common_case(['main:', 'li r0, 20', 'cmp r0, 10', 'int 0'], r0 = 20)

  def test_int(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, r0', 'int 10', 'int 0'], r0 = 0xFF, e = 1)

  def test_j(self):
    self.common_case(['main:', 'li r0, 0xFF', 'j &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF)

  def test_be(self):
    self.common_case("""
    main:
      li r0, 0xFF
      cmp r0, r0
      be &label
      li r0, 0xEE
    label:
      int 0""",
    r0 = 0xFF, e = 1)

  def test_bne(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0xDD', 'bne &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF)

  def test_bs(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0x1FF', 'bs &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF, s = 1)

  def test_bns(self):
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0xFF', 'bns &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF)

  def test_bz(self):
    self.common_case(['main:', 'li r0, 0', 'cmp r0, 0', 'bz &label', 'li r0, 0xEE', 'label:', 'int 0'], e = 1, z = 1)

  def test_bnz(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0', 'bnz &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF)

  def test_bg(self):
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0xFF', 'bg &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF)
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0xFF', 'bg &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xEE, e = 1)

  def test_bge(self):
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0xFF', 'bge &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF)
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0x1FF', 'bge &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF, e = 1)
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0x1FF', 'bge &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xEE)

  def test_bl(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0x1FF', 'bl &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF, s = 1)
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0xFF', 'bl &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xEE, e = 1)

  def test_ble(self):
    self.common_case(['main:', 'li r0, 0xFF', 'cmp r0, 0x1FF', 'ble &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0xFF, s = 1)
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0x1FF', 'ble &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF, e = 1)
    self.common_case(['main:', 'li r0, 0x1FF', 'cmp r0, 0xFF', 'bge &label', 'li r0, 0xEE', 'label:', 'int 0'], r0 = 0x1FF)

  def test_call(self):
    self.common_case(['main:', 'li r0, 0xFF', 'call &fn', 'int 0', 'fn:', 'li r0, 0xEE', 'ret'], r0 = 0xEE)

  def test_li(self):
    self.common_case(['main:', 'li r0, 0xDEAD', 'int 0'], r0 = 0xDEAD)

  def test_lw(self):
    code = [
      '  .data',
      '  .type foo, int',
      '  .int 0xDEAD',
      '  .text',
      'main:',
      '  li r0, &foo',
      '  lw r1, r0',
      '  int 0'
    ]

    self.common_case(code, r1 = 0xDEAD)

  def test_lb(self):
    code = [
      '  .data',
      '  .type foo, int',
      '  .int 0xDEAD',
      '  .text',
      'main:',
      '  li r0, &foo',
      '  lb r1, r0',
      '  int 0'
    ]

    self.common_case(code, r1 = 0xAD)

  def test_stw(self):
    code = [
      '  .data',
      '  .type foo, int',
      '  .int 0xF00',
      '  .text',
      'main:',
      '  li r0, &foo',
      '  lw r1, r0',
      '  li r2, 0xDEAD',
      '  stw r0, r2',
      '  int 0',
    ]

    self.common_case(code, r1 = 0xF00, r2 = 0xDEAD, mm = {'0x020000': 0xDEAD, '0x020002': 0})

  def test_stb(self):
    code = [
      '  .data',
      '  .type foo, int',
      '  .int 0x0',
      '  .text',
      'main:',
      '  li r0, &foo',
      '  lw r1, r0',
      '  li r2, 0xDEAD',
      '  stb r0, r2',
      '  int 0',
    ]

    self.common_case(code, r2 = 0xDEAD, mm = {'0x020000': 0xAD, '0x020002': 0})

