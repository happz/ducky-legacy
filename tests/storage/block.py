import unittest
import random
import string
import tempfile
import types

import config
import mm
import storage

from mm import ADDR_FMT, segment_addr_to_addr
from tests import run_machine, common_run_machine, assert_registers, assert_flags, assert_mm, assert_file_content, prepare_file

class Tests(unittest.TestCase):
  def common_case(self, code, storages, mm, files, **kwargs):
    if type(code) == types.ListType:
      code = '\n'.join(code)

    machine_config = config.MachineConfig()

    for driver, id, path in storages:
      machine_config.add_storage(driver, id, filepath = path)

    state = common_run_machine(code, machine_config = machine_config)

    assert_registers(state.core_states[0], **kwargs)
    assert_flags(state.core_states[0], **kwargs)
    assert_mm(state, **mm)  

    for filename, cells in files:
      assert_file_content(filename, cells)

  def test_block_read(self):
    # size of storage file
    file_size   = storage.BLOCK_SIZE * 10
    # message length
    msg_length  = 64
    # msg resides in this block
    msg_block  = random.randint(0, (file_size / storage.BLOCK_SIZE) - 1)

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))

    f_tmp = prepare_file(file_size, messages = [(msg_block * storage.BLOCK_SIZE, msg)])

    storage_desc = ('block', 1, f_tmp.name)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = {
      ADDR_FMT(segment_addr_to_addr(2, 0)): 0xFEFE,
      ADDR_FMT(segment_addr_to_addr(2, 2 + storage.BLOCK_SIZE)): 0xBFBF
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 2 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_block * storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])

    code = """
      .def INT_BLOCKIO: 1
      .def BLOCKIO_READ: 0

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
        int 0
    """.format(**{'msg_block': msg_block,
                  'msg_length': msg_length,
                  'block_size': storage.BLOCK_SIZE
                 })

    self.common_case(code, [storage_desc], mm_assert, file_assert,
                     r0 = 0, r1 = 0, r2 = msg_block, r3 = 0x0002, r4 = 1)

  def test_block_write(self):
    # size of file
    file_size   = storage.BLOCK_SIZE * 10
    # message length
    msg_length  = 64
    # msg resides in this offset
    msg_block  = random.randint(0, (file_size / storage.BLOCK_SIZE) - 1)

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))
    msg += (chr(0xBF) * (storage.BLOCK_SIZE - msg_length))

    # create file that we later mmap, filled with pseudodata
    f_tmp = prepare_file(file_size)

    storage_desc = ('block', 1, f_tmp.name)

    mm_assert = {
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, storage.BLOCK_SIZE, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_block * storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])

    code = """
      .def INT_BLOCKIO: 1
      .def BLOCKIO_WRITE: 1

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
        int 0
    """.format(**{'msg_block': msg_block,
                  'msg_length': msg_length,
                  'block_size': storage.BLOCK_SIZE,
                  'msg': msg
                 })

    self.common_case(code, [storage_desc], mm_assert, file_assert,
                     r0 = 0, r1 = 1, r3 = msg_block, r4 = 1)
