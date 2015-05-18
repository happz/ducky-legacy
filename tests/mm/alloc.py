import unittest
import random

import ducky.config
import ducky.snapshot

from tests import common_run_machine, assert_mm_pages

class Tests(unittest.TestCase):
  def common_case(self, code = None, post_boot = None, post_run = None, **kwargs):
    if code is None:
      code = 'int 0'

    machine_config = ducky.config.MachineConfig()

    common_run_machine(code, machine_config = machine_config, post_boot = post_boot, post_run = post_run)

  def test_alloc_page(self):
    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_page()

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 2, 256, 257, 512, 513])

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 2, 256, 257, 512, 513])

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_page_segment_0(self):
    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_page(segment = 0)

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 2, 256, 257, 512, 513])

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 2, 256, 257, 512, 513])

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_page_segment_other(self):
    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_page(segment = 2)

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513, 514])

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513, 514])

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_pages(self):
    cnt = random.randint(1, 20)

    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_pages(count = cnt)

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_pages_segment_0(self):
    cnt = random.randint(1, 20)

    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_pages(segment = 0, count = cnt)

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_pages_segment_other(self):
    cnt = random.randint(1, 20)

    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_pages(segment = 2, count = cnt)

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i + 512 for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *([0, 1] + [i + 512 for i in range(2, 2 + cnt)] + [256, 257, 512, 513]))

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_free_page(self):
    def __test(M):
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

      M.memory.alloc_page()

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 2, 256, 257, 512, 513])

      M.memory.free_page(M.memory.get_page(2))

      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

    def __assert_state(M, S):
      assert_mm_pages(S.get_child('machine').get_child('memory'), *[0, 1, 256, 257, 512, 513])

    self.common_case(post_boot = [__test], post_run = [__assert_state])

  def test_alloc_and_free_pages_overlap(self):
    cnt1 = 17
    cnt2 = 20
    start = 10
    cnt3 = 15

    def __test(M):
      pages = [0, 1, 256, 257, 512, 513]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = cnt1)

      pages += [i for i in range(2, 2 + cnt1)]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = cnt2)

      pages += [i for i in range(2 + cnt1, 2 + cnt1 + cnt2)]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.free_pages(M.memory.get_page(start), count = cnt3)

      for i in range(start, start + cnt3):
        pages.remove(i)
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

    self.common_case(post_boot = [__test])

  def test_alloc_pages_fit(self):
    def __test(M):
      pages = [0, 1, 256, 257, 512, 513]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = 16)

      pages += [i for i in range(2, 18)]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.free_pages(M.memory.get_page(2), 8)

      for i in range(2, 10):
        pages.remove(i)
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

      M.memory.alloc_pages(segment = 0, count = 4)

      pages += [i for i in range(2, 6)]
      S = ducky.snapshot.VMState.capture_vm_state(M, suspend = False)
      assert_mm_pages(S.get_child('machine').get_child('memory'), *pages)

    self.common_case(post_boot = [__test])
