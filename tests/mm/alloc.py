from .. import TestCase, common_run_machine, assert_mm_pages, mock, LOGGER
from ducky.mm import PAGE_SIZE, MemoryController, MINIMAL_SIZE, AnonymousMemoryPage
from ducky.errors import InvalidResourceError

from hypothesis import given, assume
from hypothesis.strategies import integers

@given(pages = integers(min_value = 0, max_value = 0x100000000 // PAGE_SIZE))
def test_memory_size(pages):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: pages=%d', pages)

  machine = mock.MagicMock()

  try:
    MemoryController(machine, size = pages * PAGE_SIZE)

  except InvalidResourceError as e:
    if pages < MINIMAL_SIZE:
      assert e.message == 'Memory size must be at least %d pages' % MINIMAL_SIZE

    else:
      raise e

@given(pages = integers(min_value = MINIMAL_SIZE, max_value = 0x100000000 // PAGE_SIZE), pg = integers(min_value = 0, max_value = 0x100000000 // PAGE_SIZE))
def test_memory_alloc_beyond(pages, pg):
  assume(pg >= pages)

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: pages=%d, pg=%d', pages, pg)

  machine = mock.MagicMock()
  mc = MemoryController(machine, size = pages * PAGE_SIZE)

  try:
    mc._MemoryController__set_page(AnonymousMemoryPage(mc, pg))

  except InvalidResourceError as e:
    assert e.message == 'Attempt to create page with index out of bounds: pg.index=%d' % pg

  else:
    assert False, 'InvalidResourceError exception expected, none appeared'

class Tests(TestCase):
  def test_alloc_page(self):
    def __test(M):
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1])

      pg_index = 79
      M.memory.alloc_specific_page(pg_index)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1, pg_index])

      return False

    common_run_machine(post_boot = [__test])

  def test_touch_page(self):
    def __test(M):
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1])

      pg_index = 79
      M.memory.write_u32(pg_index * PAGE_SIZE + 16, 0xFADEABCA)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1, pg_index])

      return False

    common_run_machine(post_boot = [__test])

  def test_free_page(self):
    def __test(M):
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1])

      pg_index = 79
      pg = M.memory.alloc_specific_page(pg_index)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1, pg_index])

      M.memory.free_page(pg)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[1])

      return False

    common_run_machine(post_boot = [__test])
