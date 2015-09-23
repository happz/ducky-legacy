import unittest
import random
import string
import os

import ducky.config
import ducky.devices.storage

from ducky.mm import ADDR_FMT, segment_addr_to_addr
from tests import common_run_machine, assert_registers, assert_flags, assert_mm, assert_file_content, prepare_file

class Tests(unittest.TestCase):
  def common_case(self, code = None, binary = None, storages = None, mm = None, files = None, **kwargs):
    files = files or []

    machine_config = ducky.config.MachineConfig()

    for driver, id, path in storages:
      machine_config.add_storage(driver, id, filepath = path)

    def __assert_state(M, S):
      assert_registers(S.get_child('machine').get_child('core0'), **kwargs)
      assert_flags(S.get_child('machine').get_child('core0'), **kwargs)

      if mm:
        assert_mm(S.get_child('machine').get_child('memory'), **mm)

      for filename, cells in files:
        assert_file_content(filename, cells)

    common_run_machine(code = code, binary = binary, machine_config = machine_config, post_run = [__assert_state])

  def test_unknown_device(self):
    file_size = ducky.devices.storage.BLOCK_SIZE * 10
    f_tmp = prepare_file(file_size)
    storage_desc = ('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)

    self.common_case(binary = os.path.join(os.getenv('CURDIR'), 'tests', 'storage', 'test_unknown_device_1.bin'), storages = [storage_desc], r0 = 0xFFFF, z = 1)

  def test_out_of_bounds_access(self):
    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100

    file_size = ducky.devices.storage.BLOCK_SIZE * 10
    f_tmp = prepare_file(file_size)
    storage_desc = ('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)

    self.common_case(binary = os.path.join(os.getenv('CURDIR'), 'tests', 'storage', 'test_out_of_bounds_access_read.bin'), storages = [storage_desc], r0 = 0xFFFF, r2 = 16, r3 = data_base, r4 = 1)
    self.common_case(binary = os.path.join(os.getenv('CURDIR'), 'tests', 'storage', 'test_out_of_bounds_access_write.bin'), storages = [storage_desc], r0 = 0xFFFF, r1 = 1, r2 = 16, r3 = data_base, r4 = 1)

  def test_block_read(self):
    # size of storage file
    file_size   = ducky.devices.storage.BLOCK_SIZE * 10
    # message length
    msg_length  = 64
    # msg resides in this block
    msg_block  = random.randint(0, (file_size / ducky.devices.storage.BLOCK_SIZE) - 1)

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))

    f_tmp = prepare_file(file_size, messages = [(msg_block * ducky.devices.storage.BLOCK_SIZE, msg)])

    storage_desc = ('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = {
      ADDR_FMT(segment_addr_to_addr(2, 0x0100)): 0xFEFE,
      ADDR_FMT(segment_addr_to_addr(2, 0x0102 + ducky.devices.storage.BLOCK_SIZE)): 0xBFBF
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 0x0102 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])

    code = """
      .include "defs.asm"

      .def MSG_BLOCK:  {msg_block}
      .def MSG_LENGTH: {msg_length}
      .def BLOCK_SIZE: {block_size}

        .data
        .type redzone_pre, int
        .int 0xFEFE

        .type block, space
        .space $BLOCK_SIZE

        .type redzone_post, int
        .int 0xBFBF

        .text

      main:
        li r0, 1
        li r1, $BLOCKIO_READ
        li r2, $MSG_BLOCK
        li r3, &block
        li r4, 1
        int $INT_BLOCKIO
        int $INT_HALT
    """.format(**{'msg_block': msg_block, 'msg_length': msg_length, 'block_size': ducky.devices.storage.BLOCK_SIZE})

    self.common_case(code = code, storages = [storage_desc], mm = mm_assert, files = file_assert,
                     r0 = 0, r1 = 0, r2 = msg_block, r3 = 0x0102, r4 = 1)

  def test_block_write(self):
    # size of file
    file_size   = ducky.devices.storage.BLOCK_SIZE * 10
    # message length
    msg_length  = 64
    # msg resides in this offset
    msg_block  = random.randint(0, (file_size / ducky.devices.storage.BLOCK_SIZE) - 1)

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))
    msg += (chr(0xBF) * (ducky.devices.storage.BLOCK_SIZE - msg_length))

    # create file that we later mmap, filled with pseudodata
    f_tmp = prepare_file(file_size)

    storage_desc = ('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)

    mm_assert = {
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, ducky.devices.storage.BLOCK_SIZE, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 0x0100 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])

    code = """
      .include "defs.asm"

      .def MSG_BLOCK:  {msg_block}
      .def MSG_LENGTH: {msg_length}
      .def BLOCK_SIZE: {block_size}

        .data
        .type block, ascii
        .ascii "{msg}"

        .text

      main:
        li r0, 1
        li r1, $BLOCKIO_WRITE
        li r2, &block
        li r3, $MSG_BLOCK
        li r4, 1
        int $INT_BLOCKIO
        int $INT_HALT
    """.format(**{'msg_block': msg_block, 'msg_length': msg_length, 'block_size': ducky.devices.storage.BLOCK_SIZE, 'msg': msg})

    self.common_case(code = code, storages = [storage_desc], mm = mm_assert, files = file_assert,
                     r0 = 0, r1 = 1, r2 = 0x0100, r3 = msg_block, r4 = 1)
