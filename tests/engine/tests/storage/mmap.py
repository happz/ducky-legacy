import os
import random
import string

from ducky.mm import segment_addr_to_addr
from .. import TestCase, prepare_file, common_run_machine, common_asserts
from functools import partial

def common_case(mm_asserts = None, file_asserts = None, **kwargs):
  common_run_machine(post_run = [partial(common_asserts, mm_asserts = mm_asserts, file_asserts = file_asserts, **kwargs)], **kwargs)

class Tests(TestCase):
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

    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS') == 'yes' else 0x0100
    ph_data_base = segment_addr_to_addr(3, data_base)

    mmap_desc = (f_tmp.name, segment_addr_to_addr(3, mmap_offset), mmap_size, 0, 'r', False)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = [
      (ph_data_base,                      0xFEFE),
      (ph_data_base + 2 + msg_length,     0xBFBF),
      (ph_data_base + 2 + msg_length + 2, msg_offset)
    ]

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert.append((ph_data_base + 2 + i, ord(msg[i]) | (ord(msg[i + 1]) << 8)))
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])

    common_case(binary = os.path.join(os.getenv('CURDIR'), 'tests', 'storage', 'test_mmap_read.testbin'),
                mmaps = [mmap_desc],
                pokes = [(ph_data_base + 2 + msg_length + 2, msg_offset, 2)],
                mm_asserts = mm_assert, file_asserts = file_assert,
                r0 = mmap_offset + msg_offset + msg_length, r1 = data_base + 2 + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)

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

    data_base = 0x1000 if os.getenv('MMAPABLE_SECTIONS') == 'yes' else 0x0100
    ph_data_base = segment_addr_to_addr(3, data_base)

    mmap_desc = (f_tmp.name, segment_addr_to_addr(3, mmap_offset), mmap_size, 0, 'rw', True)

    mm_assert = []

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 2):
      mm_assert.append((ph_data_base + i, ord(msg[i]) | (ord(msg[i + 1]) << 8)))
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])

    common_case(binary = os.path.join(os.getenv('CURDIR'), 'tests', 'storage', 'test_mmap_write.testbin'),
                mmaps = [mmap_desc],
                pokes = [(ph_data_base + msg_length, msg_offset, 2)] + [(ph_data_base + i, ord(msg[i]), 1) for i in range(0, msg_length)],
                mm_asserts = mm_assert, file_asserts = file_assert,
                r0 = mmap_offset + msg_offset + msg_length, r1 = data_base + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)
