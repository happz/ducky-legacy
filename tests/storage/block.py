import random
import string
import os

import ducky.devices.storage

from .. import common_run_machine, prepare_file, common_asserts, TestCase
from functools import partial
from ducky.boot import DEFAULT_BOOTLOADER_ADDRESS

def common_case(mm_asserts = None, file_asserts = None, **kwargs):
  common_run_machine(post_run = [partial(common_asserts, mm_asserts = mm_asserts, file_asserts = file_asserts, **kwargs)], **kwargs)

class Tests(TestCase):
  def test_unknown_device(self):
    f_tmp = prepare_file(ducky.devices.storage.BLOCK_SIZE * 10)

    common_case(binary = os.path.join('storage', 'test_unknown_device_1'),
                storages = [('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)],
                r0 = 0x01, r1 = 0x02, r10 = 0x08)

  def test_out_of_bounds_access(self):
    f_tmp = prepare_file(ducky.devices.storage.BLOCK_SIZE * 10)

    common_case(binary = os.path.join('storage', 'test_out_of_bounds_access_read'),
                storages = [('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)],
                r0 = 0x01, r1 = 0x01, r2 = 0x02, r10 = 0x24)
    common_case(binary = os.path.join('storage', 'test_out_of_bounds_access_write'),
                storages = [('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)],
                r0 = 0x01, r1 = 0x01, r2 = 0x02, r10 = 0x28)

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

    data_base = DEFAULT_BOOTLOADER_ADDRESS + (0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100)

    # prepare mm assert dict, and insert message and redzones in front and after the buffer
    mm_assert = [
      (data_base, msg_block),
      (data_base + 4, 0xFEFEFEFE),
      (data_base + 8 + ducky.devices.storage.BLOCK_SIZE, 0xBFBFBFBF)
    ]

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, msg_length, 4):
      mm_assert.append((data_base + 8 + i, ord(msg[i]) | (ord(msg[i + 1]) << 8) | (ord(msg[i + 2]) << 16) | (ord(msg[i + 3]) << 24)))
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 2] = ord(msg[i + 2])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 3] = ord(msg[i + 3])

    common_case(binary = os.path.join('storage', 'test_block_read'),
                storages = [storage_desc], pokes = [(data_base, msg_block, 4)],
                mm_asserts = mm_assert, file_asserts = file_assert,
                r0 = 0x01, r1 = 0x01, r2 = 0x01, r10 = 0x24)

  def test_block_write(self):
    # size of file
    file_size   = ducky.devices.storage.BLOCK_SIZE * 10
    # message length
    msg_length  = 64
    # msg resides in this offset
    msg_block  = random.randint(0, (file_size / ducky.devices.storage.BLOCK_SIZE) - 1)

    # create random message
    msg = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(msg_length))
    msg += (chr(0x61) * (ducky.devices.storage.BLOCK_SIZE - msg_length))

    # create file that we later mmap, filled with pseudodata
    f_tmp = prepare_file(file_size)

    storage_desc = ('ducky.devices.storage.FileBackedStorage', 1, f_tmp.name)

    data_base = DEFAULT_BOOTLOADER_ADDRESS + (0x1000 if os.getenv('MMAPABLE_SECTIONS')  == 'yes' else 0x0100)

    mm_assert = []

    file_assert = [
      (f_tmp.name, {})
    ]

    for i in range(0, ducky.devices.storage.BLOCK_SIZE, 4):
      mm_assert.append((data_base + 4 + i, ord(msg[i]) | (ord(msg[i + 1]) << 8) | (ord(msg[i + 2]) << 16) | (ord(msg[i + 3]) << 24)))
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i] = ord(msg[i])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 1] = ord(msg[i + 1])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 2] = ord(msg[i + 2])
      file_assert[0][1][msg_block * ducky.devices.storage.BLOCK_SIZE + i + 3] = ord(msg[i + 3])

    common_case(binary = os.path.join('storage', 'test_block_write'),
                storages = [storage_desc], pokes = [(data_base, msg_block, 4)] + [(data_base + 4 + i, ord(msg[i]), 1) for i in range(0, ducky.devices.storage.BLOCK_SIZE)],
                mm_asserts = mm_assert, file_assertss = file_assert,
                r0 = 0x01, r1 = 0x01, r2 = 0x01, r10 = 0x28)
