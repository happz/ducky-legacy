import random

from .. import TestCase, common_run_machine, assert_mm_pages

class Tests(TestCase):
  def test_alloc_page(self, segment = None):
    def __test(M):
      S = M.capture_state()
      S.print_node()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257])

      pg = M.memory.alloc_page(segment = segment)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257, pg.index])

      return False

    common_run_machine(post_boot = [__test])

  def test_alloc_page_segment_protected(self):
    self.test_alloc_page(segment = 0)

  def test_alloc_page_segment_user(self):
    self.test_alloc_page(segment = 2)

  def test_alloc_pages(self, segment = None):
    cnt = random.randint(1, 20)

    def __test(M):
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257])

      pgs = M.memory.alloc_pages(segment = segment, count = cnt)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 256, 257] + [pg.index for pg in pgs]))

      return False

    common_run_machine(post_boot = [__test])

  def test_alloc_pages_segment_protected(self):
    self.test_alloc_pages(segment = 0)

  def test_alloc_pages_segment_user(self):
    self.test_alloc_pages(segment = 2)

  def test_free_page(self, segment = None):
    def __test(M):
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257])

      pg = M.memory.alloc_page(segment = segment)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257, pg.index])

      M.memory.free_page(pg)

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 256, 257])

      return False

    common_run_machine(post_boot = [__test])

  def test_free_page_segment_protected(self):
    self.test_free_page(segment = 0)

  def test_free_page_segment_user(self):
    self.test_free_page(segment = 2)

  def test_alloc_and_free_pages_overlap(self):
    cnt1 = 17
    cnt2 = 20
    start = 10
    cnt3 = 15

    def __test(M):
      pages = [0, 256, 257]
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = cnt1)

      pages += [i for i in range(1, 1 + cnt1)]
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = cnt2)

      pages += [i for i in range(1 + cnt1, 1 + cnt1 + cnt2)]
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.free_pages(M.memory.page(start), count = cnt3)

      for i in range(start, start + cnt3):
        pages.remove(i)
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      return False

    common_run_machine(post_boot = [__test])

  def test_alloc_pages_fit(self):
    def __test(M):
      pages = [0, 256, 257]

      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = 16)

      pages += [i for i in range(1, 17)]
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.free_pages(M.memory.page(1), 8)

      for i in range(1, 9):
        pages.remove(i)
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = 4)

      pages += [i for i in range(1, 5)]
      S = M.capture_state()
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      return False

    common_run_machine(post_boot = [__test])
