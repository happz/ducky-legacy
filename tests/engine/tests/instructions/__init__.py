import os

from ducky.mm import segment_addr_to_addr

from .. import common_run_machine, common_asserts, TestCase
from functools import partial

def common_case(mm_asserts = None, **kwargs):
  kwargs['binary'] = os.path.join(os.getenv('CURDIR'), 'tests', 'instructions', 'tests', kwargs['binary'] + '.testbin')
  common_run_machine(post_run = [partial(common_asserts, mm_asserts = mm_asserts, **kwargs)], **kwargs)

class Tests(TestCase):
  def test_nop(self):
    common_case(binary = 'nop_1', r0 = 0x100)

  def test_inc(self):
    common_case(binary = 'inc_1', r0 = 1)
    common_case(binary = 'inc_2', r0 = 2)
    common_case(binary = 'inc_3', r0 = 0xFFFF, s = 1)
    common_case(binary = 'inc_4', r0 = 0, z = 1)

  def test_dec(self):
    common_case(binary = 'dec_1', z = 1)
    common_case(binary = 'dec_2', r0 = 0xFFFF, s = 1)
    common_case(binary = 'dec_3', r0 = 1)

  def test_add(self):
    common_case(binary = 'add_1', r0 = 15, r1 = 10)
    common_case(binary = 'add_2', r1 = 2, o = 1, z = 1)
    common_case(binary = 'add_3', r0 = 2, r1 = 4, o = 1)
    common_case(binary = 'add_4', r0 = 15)
    common_case(binary = 'add_5', o = 1, z = 1)
    common_case(binary = 'add_6', r0 = 2, o = 1)

  def test_sub(self):
    common_case(binary = 'sub_1', r0 = 10, r1 = 5)
    common_case(binary = 'sub_2', r0 = 0, r1 = 2, z = 1)
    common_case(binary = 'sub_3', r0 = 0xFFFE, r1 = 4, s = 1)
    common_case(binary = 'sub_4', r0 = 10)
    common_case(binary = 'sub_5', z = 1)
    common_case(binary = 'sub_6', r0 = 0xFFFE, s = 1)

  def test_mul(self):
    common_case(binary = 'mul_1', r0 = 15, r1 = 3)
    common_case(binary = 'mul_2', r0 = 15)
    common_case(binary = 'mul_3', z = 1)
    common_case(binary = 'mul_4', z = 1)

  def test_div(self):
    common_case(binary = 'div_1', r0 = 5, r1 = 2)
    common_case(binary = 'div_2', r0 = 5)
    common_case(binary = 'div_3', r1 = 2, z = 1)
    common_case(binary = 'div_4', z = 1)
    common_case(binary = 'div_5', r1 = 20, z = 1)
    common_case(binary = 'div_6', z = 1)
    # TODO: division by zeor

  def test_mod(self):
    common_case(binary = 'mod_1', r1 = 1, z = 1)
    common_case(binary = 'mod_2', z = 1)
    common_case(binary = 'mod_3', r1 = 2, z = 1)
    common_case(binary = 'mod_4', z = 1)
    common_case(binary = 'mod_5', r0 = 1, r1 = 3)
    common_case(binary = 'mod_6', r0 = 1)
    common_case(binary = 'mod_7', r0 = 2, r1 = 4)
    common_case(binary = 'mod_8', r0 = 2)

  def test_and(self):
    common_case(binary = 'and_1', r0 = 0x0008, r1 = 0x0008)
    common_case(binary = 'and_2', r1 = 0x0004, z = 1)
    common_case(binary = 'and_3', r0 = 0x0008)
    common_case(binary = 'and_4', z = 1)

  def test_or(self):
    common_case(binary = 'or_1', r0 = 0xFFFF, r1 = 0x000F, s = 1)
    common_case(binary = 'or_2', r0 = 0xFFF0, r1 = 0x00F0, s = 1)
    common_case(binary = 'or_3', r0 = 0xFFFF, s = 1)
    common_case(binary = 'or_4', r0 = 0xFFF0, s = 1)

  def test_xor(self):
    common_case(binary = 'xor_1', r0 = 0x0FFF, r1 = 0x0F0F)
    common_case(binary = 'xor_2', r0 = 0x0FFF)
    common_case(binary = 'xor_3', r0 = 0x0F00, r1 = 0x0FF0)
    common_case(binary = 'xor_4', r0 = 0x0F00)
    common_case(binary = 'xor_5', z = 1)

  def test_not(self):
    common_case(binary = 'not_1', r0 = 0x000F)
    common_case(binary = 'not_2', r0 = 0xFFFF, s = 1)
    common_case(binary = 'not_3', z = 1)

  def test_shiftl(self):
    common_case(binary = 'shiftl_1', r0 = 2)
    common_case(binary = 'shiftl_2', r0 = 16)
    common_case(binary = 'shiftl_3', z = 1)
    common_case(binary = 'shiftl_4', z = 1)
    common_case(binary = 'shiftl_5', r0 = 0x0F00)

  def test_shiftr(self):
    common_case(binary = 'shiftr_1', r0 = 1)
    common_case(binary = 'shiftr_2', r0 = 1)
    common_case(binary = 'shiftr_3', z = 1)
    common_case(binary = 'shiftr_4', z = 1)
    common_case(binary = 'shiftr_5', r0 = 0x000F)

  def test_mov(self):
    common_case(binary = 'mov_1', r0 = 20, r1 = 20)
    common_case(binary = 'mov_2', z = 1)

  def test_swap(self):
    common_case(binary = 'swap_1', r0 = 20, r1 = 10)

  def test_cmp(self):
    common_case(binary = 'cmp_1', e = 1, z = 1)
    common_case(binary = 'cmp_2', e = 1, z = 1)
    common_case(binary = 'cmp_3', r0 = 1, e = 1)
    common_case(binary = 'cmp_4', r0 = 1, e = 1)
    common_case(binary = 'cmp_5', r0 = 1)
    common_case(binary = 'cmp_6', r0 = 1)
    common_case(binary = 'cmp_7', r0 = 10, r1 = 20, s = 1)
    common_case(binary = 'cmp_8', r0 = 10, s = 1)
    common_case(binary = 'cmp_9', r0 = 20, r1 = 10)
    common_case(binary = 'cmp_10', r0 = 20)

  def test_int(self):
    common_case(binary = 'int_1', r0 = 0xFF, r1 = 0xDD, e = 1)

  def test_j(self):
    common_case(binary = 'j_1', r0 = 0xFF)

  def test_be(self):
    common_case(binary = 'be_1', r0 = 0xFF, e = 1)

  def test_bne(self):
    common_case(binary = 'bne_1', r0 = 0xFF)

  def test_bs(self):
    common_case(binary = 'bs_1', r0 = 0xFF, s = 1)

  def test_bns(self):
    common_case(binary = 'bns_1', r0 = 0x1FF)

  def test_bz(self):
    common_case(binary = 'bz_1', e = 1, z = 1)

  def test_bnz(self):
    common_case(binary = 'bnz_1', r0 = 0xFF)

  def test_bo(self):
    common_case(binary = 'bo', r0 = 1, r1 = 0xDD)

  def test_bno(self):
    common_case(binary = 'bno', r0 = 0x2, r1 = 0xDD)

  def test_bg(self):
    common_case(binary = 'bg_1', r0 = 0x1FF)
    common_case(binary = 'bg_2', r0 = 0xEE, e = 1)

  def test_bge(self):
    common_case(binary = 'bge_1', r0 = 0x1FF)
    common_case(binary = 'bge_2', r0 = 0x1FF, e = 1)
    common_case(binary = 'bge_3', r0 = 0xEE)

  def test_bl(self):
    common_case(binary = 'bl_1', r0 = 0xFF, s = 1)
    common_case(binary = 'bl_2', r0 = 0xEE, e = 1)

  def test_ble(self):
    common_case(binary = 'ble_1', r0 = 0xFF, s = 1)
    common_case(binary = 'ble_2', r0 = 0x1FF, e = 1)
    common_case(binary = 'ble_3', r0 = 0x1FF)

  def test_call(self):
    common_case(binary = 'call_1', r0 = 0xEE)

  def test_li(self):
    common_case(binary = 'li_1', r0 = 0xDEAD, s = 1)

  def test_lw(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100
    common_case(binary = 'lw_1', r0 = data_base, r1 = 0xDEAD, s = 1)

  def test_lb(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100
    common_case(binary = 'lb_1', r0 = data_base + 2, r1 = 0xAD)
    common_case(binary = 'lb_2', r0 = data_base + 3, r1 = 0xDE)

  def test_stw(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100
    ph_data_base = segment_addr_to_addr(3, data_base)

    common_case(binary = 'stw_1', r0 = data_base, r1 = 0xF00, r2 = 0xDEAD, s = 1, mm_asserts = [(ph_data_base, 0xDEAD), (ph_data_base + 2, 0)])

  def test_stb(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100
    ph_data_base = segment_addr_to_addr(3, data_base)

    common_case(binary = 'stb_1', r0 = data_base, r2 = 0xDEAD, s = 1, mm_asserts = [(ph_data_base, 0xAD), (ph_data_base + 2, 0)])
    common_case(binary = 'stb_2', r0 = data_base + 1, r2 = 0xDE,      mm_asserts = [(ph_data_base, 0xDE00)])

  def test_cli(self):
    fp = 0x1100 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0200
    common_case(binary = 'cli_1', r0 = 0x100, r1 = 0xFF, fp = fp, sp = fp, cs = 0x03, ds = 0x03, privileged = 0)
    common_case(binary = 'cli_2', r0 = 0x100, r1 = 0xFF, hwint = 0)

  def test_sti(self):
    # hwint is always 1... This is just a sanity test, nothing serious.
    # But it's better than nothing.

    common_case(binary = 'sti_1', r0 = 0x100)

  def test_cas(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS') == 'yes' else 0x0100
    ph_data_base = segment_addr_to_addr(3, data_base)

    common_case(binary  ='cas_1', r0 = 0x100, r1 = data_base, r2 = 0x0A, r3 = 0x0B, e = 1, mm_asserts = [(ph_data_base, 0x0B)])
    common_case(binary = 'cas_2', r0 = 0x100, r1 = data_base, r2 = 0x0A, r3 = 0x0C, mm_asserts = [(ph_data_base, 0x0A)])

  def test_sete(self):
    common_case(binary = 'sete_1', r0 = 0xFF, r1 = 1, e = 1, z = 1)

  def test_seto(self):
    common_case(binary = 'seto_1', r0 = 1, r1 = 1, z = 1)

  def test_setz(self):
    common_case(binary = 'setz_1', r1 = 1, z = 1)

  def test_sets(self):
    common_case(binary = 'sets_1', r0 = 0xEE, r1 = 1, z = 1)

  def test_setl(self):
    common_case(binary = 'setl', r0 = 0xEE, r1 = 1, z = 1)

  def test_setle(self):
    common_case(binary = 'setle', r0 = 0xEE, r1 = 1, r2 = 1, z = 1)

  def test_setg(self):
    common_case(binary = 'setg', r0 = 0xEE, r1 = 1, z = 1)

  def test_setge(self):
    common_case(binary = 'setge', r0 = 0xEE, r1 = 1, r2 = 1, z = 1)
