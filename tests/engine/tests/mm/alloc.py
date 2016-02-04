from .. import TestCase, common_run_machine, assert_mm_pages
from ducky.mm import PAGE_SIZE

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
