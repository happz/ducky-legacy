"""
Persistent storage support.

Several different persistent storages can be attached to a virtual machine, each
with its own id. This module provides methods for manipulating their content. By
default, storages operate with blocks of constant, standard size, though this is
not a mandatory requirement - storage with different block size, or even with
variable block size can be implemented.

Each block has its own id. Block IO operations read or write one or more blocks to
or from a device. IO is requested by invoking the virtual interrupt, with properly
set values in registers.
"""

import os
import six

from ..errors import InvalidResourceError
from ..interfaces import IVirtualInterrupt
from ..cpu.registers import Registers
from . import IRQList, VIRTUAL_INTERRUPTS
from ..mm import segment_addr_to_addr
from ..util import Flags, str2bytes
from . import Device

from ctypes import c_ushort

#: Size of block, in bytes.
BLOCK_SIZE = 1024

class StorageAccessError(Exception):
  """
  Base class for storage-related exceptions.
  """

  pass

class Storage(Device):
  """
  Base class for all block storages.

  :param ducky.machine.Machine machine: machine storage is attached to.
  :param int sid: id of storage.
  :param int size: size of storage, in bytes.
  """

  def __init__(self, machine, name, sid = None, size = None, *args, **kwargs):
    super(Storage, self).__init__(machine, 'storage', name, *args, **kwargs)

    self.sid = sid
    self.size = size

  def do_read_block(self, src, dst, cnt):
    """
    Read one or more blocks from device to memory.

    Child classes are supposed to reimplement this particular method.

    :param u16 src: block id of the first block
    :param u24 dst: destination buffer address
    :param int cnt: number of blocks to read
    """

    raise NotImplementedError()

  def do_write_block(self, src, dst, cnt):
    """
    Write one or more blocks from memory to device.

    Child classes are supposed to reimplement this particular method.

    :param u24 src: source buffer address
    :param uin16 dst: block id of the first block
    :param int cnt: number of blocks to write
    """

    raise NotImplementedError()

  def read_block(self, src, dst, cnt):
    """
    Read one or more blocks from device to memory.

    Child classes should not reimplement this method, as it provides checks
    common for (probably) all child classes.

    :param u16 src: block id of the first block
    :param u24 dst: destination buffer address
    :param int cnt: number of blocks to read
    """

    self.machine.DEBUG('read_block: id=%s, src=%s, dst=%s, cnt=%s', self.sid, src, dst, cnt)

    if (src + cnt) * BLOCK_SIZE > self.size:
      raise StorageAccessError('Out of bounds access: storage size {} is too small'.format(self.size))

    self.do_read_block(src, dst, cnt)

  def write_block(self, src, dst, cnt):
    """
    Write one or more blocks from memory to device.

    Child classes should not reimplement this method, as it provides checks
    common for (probably) all child classes.

    :param u24 src: source buffer address
    :param uin16 dst: block id of the first block
    :param int cnt: number of blocks to write
    """

    self.machine.DEBUG('write_block: id=%s, src=%s, dst=%s, cnt=%s', self.sid, src, dst, cnt)

    if (dst + cnt) * BLOCK_SIZE > self.size:
      raise StorageAccessError('Out of bounds access: storage size {} is too small'.format(self.size))

    self.do_write_block(src, dst, cnt)

class FileBackedStorage(Storage):
  """
  Storage that saves its content into a regular file.
  """

  def __init__(self, machine, name, filepath = None, *args, **kwargs):
    """
    :param machine.Machine machine: virtual machine this storage is attached to
    :param int sid: storage id
    :param path: path to a underlying file
    """

    self.filepath = filepath
    st = os.stat(filepath)

    super(FileBackedStorage, self).__init__(machine, name, size = st.st_size, *args, **kwargs)

    self.filepath = filepath
    self.file = None

  @staticmethod
  def create_from_config(machine, config, section):
    return FileBackedStorage(machine, section, sid = config.getint(section, 'sid', None), filepath = config.get(section, 'filepath', None))

  def boot(self):
    self.machine.DEBUG('FileBackedStorage.boot')

    self.file = open(self.filepath, 'r+b')

    self.machine.INFO('storage: file %s as storage #%i (%s)', self.filepath, self.sid, self.name)

  def halt(self):
    self.machine.DEBUG('FileBackedStorage.halt')

    self.file.flush()
    self.file.close()

  def do_read_block(self, src, dst, cnt):
    self.machine.DEBUG('do_read_block: src=%s, dst=%s, cnt=%s', src, dst, cnt)

    self.file.seek(src * BLOCK_SIZE)
    buff = self.file.read(cnt * BLOCK_SIZE)

    if six.PY2:
      for c in buff:
        self.machine.memory.write_u8(dst, ord(c))
        dst += 1

    else:
      for c in buff:
        self.machine.memory.write_u8(dst, int(c))
        dst += 1

    self.machine.DEBUG('BIO: %s bytes read from %s:%s', cnt * BLOCK_SIZE, self.file.name, dst * BLOCK_SIZE)

  def do_write_block(self, src, dst, cnt):
    buff = []

    for _ in range(0, cnt * BLOCK_SIZE):
      buff.append(chr(self.machine.memory.read_u8(src)))
      src += 1

    buff = ''.join(buff)

    self.file.seek(dst * BLOCK_SIZE)
    self.file.write(str2bytes(buff))
    self.file.flush()

    self.machine.DEBUG('BIO: %s bytes written at %s:%s', cnt * BLOCK_SIZE, self.file.name, dst * BLOCK_SIZE)

class BlockIOFlags(Flags):
  """
  Flags accepted by block IO interrupt.
  """

  _fields_ = [
    ('direction', c_ushort, 1),
    ('async',     c_ushort, 1)
  ]

class BlockIOInterrupt(IVirtualInterrupt):
  """
  Virtual interrupt handler of block IO.
  """

  def run(self, core):
    """
    Execute requested IO operation. Arguments are passed in registers:

    - ``r0`` - device id
    - ``r1`` - flags
    - ``r2`` - read: block id, write: src memory address
    - ``r3`` - read: dst memory address, write: block id
    - ``r4`` - number of blocks

    Current data segment is used for addressing memory locations.

    Success is indicated by ``0`` in ``r0``, any other value means error.
    """

    core.DEBUG('BIO requested')

    r0 = core.REG(Registers.R00)

    try:
      device = self.machine.get_storage_by_id(r0.value)
    except InvalidResourceError:
      core.WARN('BIO: unknown device: id=%s', r0.value)
      r0.value = 0xFFFF
      return

    r1 = core.REG(Registers.R01)
    r2 = core.REG(Registers.R02)
    r3 = core.REG(Registers.R03)
    r4 = core.REG(Registers.R04)
    DS = core.REG(Registers.DS)

    flags = BlockIOFlags()
    flags.load_uint16(r1.value)

    if flags.direction == 0:
      handler = device.read_block
      src = r2.value
      dst = segment_addr_to_addr(DS.value & 0xFF, r3.value)

    else:
      handler = device.write_block
      src = segment_addr_to_addr(DS.value & 0xFF, r2.value)
      dst = r3.value

    cnt = r4.value & 0x00FF

    try:
      r0.value = 0xFFFF
      handler(src, dst, cnt)
      r0.value = 0

    except StorageAccessError as e:
      core.ERROR('BIO: operation failed')
      core.EXCEPTION(e)

VIRTUAL_INTERRUPTS[IRQList.BLOCKIO.value] = BlockIOInterrupt
