import unittest
import random
import string

import ducky.config

from ducky.mm import ADDR_FMT, segment_addr_to_addr
from tests import prepare_file, common_run_machine, assert_registers, assert_flags, assert_mm, assert_file_content

class Tests(unittest.TestCase):
  def common_case(self, code, mmaps, mm, files, **kwargs):
    machine_config = ducky.config.MachineConfig()

    for path, addr, size, offset, access, shared in mmaps:
      machine_config.add_mmap(path, addr, size, offset = offset, access = access, shared = shared)

    def __assert_state(M, S):
      assert_registers(S.get_child('machine').get_child('core0'), **kwargs)
      assert_flags(S.get_child('machine').get_child('core0'), **kwargs)
      assert_mm(S.get_child('machine').get_child('memory'), **mm)

      for filename, cells in files:
        assert_file_content(filename, cells)

    common_run_machine(code, machine_config = machine_config, post_run = [__assert_state])

  def test_mmap_read(self):
    # size of mmapable file
    mmap_size   = 0x4000
    # message length
    msg_length  = 64
    # msg starts at this offset
    msg_offset  = random.randint(0, mmap_size - msg_length)
    # area will be placed at this address
    mmap_offset = 0x8000

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))

    # create file that we later mmap, filled with pseudodata
    f_tmp = prepare_file(mmap_size, messages = [(msg_offset, msg)])

    mmap_desc = (f_tmp.name, segment_addr_to_addr(2, mmap_offset), mmap_size, 0, 'r', False)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = {
      ADDR_FMT(segment_addr_to_addr(2, 0x0100)): 0xFEFE,
      ADDR_FMT(segment_addr_to_addr(2, 0x0102 + msg_length)): 0xBFBF
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 0x0102 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])

    code = """
      .def MMAP_START: {mmap_offset}
      .def MSG_OFFSET: {msg_offset}
      .def MSG_LENGTH: {msg_length}

        .data
        .type redzone_pre, int
        .int 0xFEFE

        .type buff, space
        .space $MSG_LENGTH

        .type redzone_post, int
        .int 0xBFBF

        .text

      main:
        li r0, $MMAP_START
        add r0, $MSG_OFFSET
        li r1, &buff
        li r2, $MSG_LENGTH
      copy_loop:
        cmp r2, r2
        bz &quit
        lb r3, r0
        stb r1, r3
        inc r0
        inc r1
        dec r2
        j &copy_loop
      quit:
        int 0
    """.format(**{'mmap_offset': mmap_offset, 'msg_offset': msg_offset, 'msg_length': msg_length})

    self.common_case(code, [mmap_desc], mm_assert, file_assert, r0 = mmap_offset + msg_offset + msg_length, r1 = 0x0100 + 2 + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)

  def test_mmap_write(self):
    # size of mmapable file
    mmap_size   = 0x4000
    # message length
    msg_length  = 64
    # msg starts at this offset
    msg_offset  = random.randint(0, mmap_size - msg_length)
    # area will be placed at this address
    mmap_offset = 0x8000

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))

    # create file that we later mmap, filled with pseudodata
    f_tmp = prepare_file(mmap_size)

    mmap_desc = (f_tmp.name, segment_addr_to_addr(2, mmap_offset), mmap_size, 0, 'w', True)

    mm_assert = {
    }

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 0x0100 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])

    code = """
      .def MMAP_START: {mmap_offset}
      .def MSG_OFFSET: {msg_offset}
      .def MSG_LENGTH: {msg_length}

        .data
        .type buff, ascii
        .ascii "{msg}"

        .text

      main:
        li r0, $MMAP_START
        add r0, $MSG_OFFSET
        li r1, &buff
        li r2, $MSG_LENGTH
      copy_loop:
        cmp r2, r2
        bz &quit
        lb r3, r1
        stb r0, r3
        inc r0
        inc r1
        dec r2
        j &copy_loop
      quit:
        int 0
    """.format(**{'mmap_offset': mmap_offset, 'msg_offset': msg_offset, 'msg_length': msg_length, 'msg': msg})

    self.common_case(code, [mmap_desc], mm_assert, file_assert, r0 = mmap_offset + msg_offset + msg_length, r1 = 0x0100 + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)
