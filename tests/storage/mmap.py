import os
import random
import string

from .. import TestCase, prepare_file, common_run_machine, common_asserts, tests_dir
from functools import partial
from ducky.boot import DEFAULT_BOOTLOADER_ADDRESS

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

    data_base = DEFAULT_BOOTLOADER_ADDRESS + (0x1000 if os.getenv('MMAPABLE_SECTIONS') == 'yes' else 0x0100)

    mmap_desc = (f_tmp.name, mmap_offset, mmap_size, 0, 'r', False)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = [
      (data_base,                      0xFEFEFEFE),
      (data_base + 4 + msg_length,     0xBFBFBFBF),
      (data_base + 4 + msg_length + 4, msg_offset)
    ]

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 4):
      mm_assert.append((data_base + 4 + i, ord(msg[i]) | (ord(msg[i + 1]) << 8) | (ord(msg[i + 2]) << 16) | (ord(msg[i + 3]) << 24)))
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])
      file_assert[0][1][msg_offset + i + 2] = ord(msg[i + 2])
      file_assert[0][1][msg_offset + i + 3] = ord(msg[i + 3])

    common_case(binary = tests_dir('storage', 'test_mmap_read'),
                mmaps = [mmap_desc],
                pokes = [(data_base + 4 + msg_length + 4, msg_offset, 4)],
                mm_asserts = mm_assert, file_asserts = file_assert,
                r0 = mmap_offset + msg_offset + msg_length, r1 = data_base + 4 + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)

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

    data_base = DEFAULT_BOOTLOADER_ADDRESS + (0x1000 if os.getenv('MMAPABLE_SECTIONS') == 'yes' else 0x0100)

    mmap_desc = (f_tmp.name, mmap_offset, mmap_size, 0, 'rw', True)

    mm_assert = []

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 4):
      mm_assert.append((data_base + i, ord(msg[i]) | (ord(msg[i + 1]) << 8) | (ord(msg[i + 2]) << 16) | (ord(msg[i + 3]) << 24)))
      file_assert[0][1][msg_offset + i] = ord(msg[i])
      file_assert[0][1][msg_offset + i + 1] = ord(msg[i + 1])
      file_assert[0][1][msg_offset + i + 2] = ord(msg[i + 2])
      file_assert[0][1][msg_offset + i + 3] = ord(msg[i + 3])

    common_case(binary = tests_dir('storage', 'test_mmap_write'),
                mmaps = [mmap_desc],
                pokes = [(data_base + msg_length, msg_offset, 4)] + [(data_base + i, ord(msg[i]), 1) for i in range(0, msg_length)],
                mm_asserts = mm_assert, file_asserts = file_assert,
                r0 = mmap_offset + msg_offset + msg_length, r1 = data_base + msg_length, r3 = ord(msg[-1]), e = 1, z = 1)
