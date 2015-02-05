import unittest
import random
import string
import tempfile
import types

import mm

from mm import ADDR_FMT, segment_addr_to_addr
from tests import run_machine, assert_registers, assert_flags, assert_mm

class Tests(unittest.TestCase):
  def common_case(self, code, mmaps, **kwargs):
    if type(code) == types.ListType:
      code = '\n'.join(code)

    state = run_machine(code, cpus = 1, cores = 1, irq_routines = 'tests/instructions/interrupts-basic.bin', mmaps = mmaps)
    assert_registers(state.core_states[0], **kwargs)
    assert_flags(state.core_states[0], **kwargs)

    if 'mm' in kwargs:
      assert_mm(state, **kwargs['mm'])

  def test_read(self):
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
    f_tmp = tempfile.NamedTemporaryFile('w+b', delete = False)
    f_tmp.seek(0)
    for _ in range(0, mmap_size):
      f_tmp.write(chr(0xDE))

    # write out the message
    f_tmp.seek(msg_offset)
    for i in range(0, msg_length):
      f_tmp.write(msg[i])

    f_tmp.close()

    mmap_desc = (f_tmp.name, segment_addr_to_addr(2, mmap_offset), mmap_size, 0, 'r', False)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = {
      ADDR_FMT(segment_addr_to_addr(2, 0)): 0xFEFE,
      ADDR_FMT(segment_addr_to_addr(2, 2 + msg_length)): 0xBFBF
    }

    for i in range(0, msg_length, 2):
      mm_assert[ADDR_FMT(segment_addr_to_addr(2, 2 + i))] = ord(msg[i]) | (ord(msg[i + 1]) << 8)

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

    self.common_case(code, [mmap_desc], r0 = mmap_offset + msg_offset + msg_length, r1 = 2 + msg_length, r3 = ord(msg[-1]), e = 1, z = 1, mm = mm_assert)

