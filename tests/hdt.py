import ducky.config
import ducky.boot
import ducky.mm

from hypothesis import given
from hypothesis.strategies import integers

from ctypes import sizeof
from . import common_run_machine, LOGGER
from functools import partial

def setup_machine(cpus, cores, memory):
  machine_config = ducky.config.MachineConfig()
  machine_config.add_section('memory')
  machine_config.set('memory', 'size', memory)

  M = common_run_machine(machine_config = machine_config, cpus = cpus, cores = cores, post_boot = [lambda _M: False])
  return M

@given(cpus = integers(min_value = 0, max_value = 0xF), cores = integers(min_value = 0, max_value = 0xF), memory = integers(min_value = ducky.mm.MINIMAL_SIZE * ducky.mm.PAGE_SIZE, max_value = 0xFFFFFF00))
def test_sanity(cpus, cores, memory):
  memory &= ducky.mm.PAGE_MASK

  LOGGER.debug('TEST: cpus=%d, cores=%d, memory=0x%08X', cpus, cores, memory)

  M = setup_machine(cpus, cores, memory)

  assert M.nr_cpus == cpus
  assert M.nr_cores == cores

  S = M.capture_state()

  memory_node = S.get_child('machine').get_child('memory')

  hdt_page = ducky.boot.DEFAULT_HDT_ADDRESS // ducky.mm.PAGE_SIZE
  hdt_page = [pg_node for pg_node in memory_node.get_page_states() if pg_node.index == hdt_page][0]

  hdt_page.print_node()

  def __base_assert(size, page, offset, value):
    for i, byte_offset, byte_shift in [(1, 0, 0), (2, 1, 8), (3, 2, 16), (4, 3, 24)]:
      expected = (value >> byte_shift) & 0xFF
      actual   = page.content[offset + byte_offset]

      assert expected == actual, 'Byte at offset %d + %d expected 0x%02X, 0x%02X found instead' % (offset, byte_offset, expected, actual)

      if i == size:
        break

  __assert_u16 = partial(__base_assert, 2, hdt_page)
  __assert_u32 = partial(__base_assert, 4, hdt_page)

  from ducky.mm import u16_t, u32_t

  ptr = 0

  # HDT header - magic
  __assert_u32(ptr, ducky.hdt.HDT_MAGIC); ptr += sizeof(u32_t)

  # HDT header - entries count
  __assert_u32(ptr, 2); ptr += sizeof(u32_t)

  # HDT header - length
  __assert_u32(ptr, 28); ptr += sizeof(u32_t)

  # Memory
  __assert_u16(ptr, ducky.hdt.HDTEntryTypes.MEMORY); ptr += sizeof(u16_t)
  __assert_u16(ptr, sizeof(ducky.hdt.HDTEntry_Memory)); ptr += sizeof(u16_t)
  __assert_u32(ptr, memory); ptr += sizeof(u32_t)

  # CPU
  __assert_u16(ptr, ducky.hdt.HDTEntryTypes.CPU); ptr += sizeof(u16_t)
  __assert_u16(ptr, sizeof(ducky.hdt.HDTEntry_CPU)); ptr += sizeof(u16_t)
  __assert_u16(ptr, cpus); ptr += sizeof(u16_t)
  __assert_u16(ptr, cores); ptr += sizeof(u16_t)
