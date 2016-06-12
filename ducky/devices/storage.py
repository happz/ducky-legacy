"""
Persistent storage support.

Several different persistent storages can be attached to a virtual machine, each
with its own id. This module provides methods for manipulating their content.
Storages operate with blocks of constant, standard size, though this is not
a mandatory requirement - storage with different block size, or even with variable
block size can be implemented.

Block IO subsystem transfers blocks between storages and VM,
"""

import enum
import os
import six

from ..errors import InvalidResourceError
from . import Device, MMIOMemoryPage
from ..util import UINT8_FMT, UINT32_FMT
from ..mm import addr_to_page

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

  def do_read_blocks(self, start, cnt):
    """
    Read one or more blocks from device to internal buffer.

    Child classes are supposed to reimplement this particular method.

    :param u32_t start: index of the first requested block.
    :param u32_t cnt: number of blocks to read.
    """

    raise NotImplementedError()

  def do_write_blocks(self, start, cnt, buff):
    """
    Write one or more blocks from internal buffer to device.

    Child classes are supposed to reimplement this particular method.

    :param u32_t start: index of the first requested block.
    :param u32_t cnt: number of blocks to write.
    """

    raise NotImplementedError()

  def read_blocks(self, start, cnt):
    """
    Read one or more blocks from device to internal buffer.

    Child classes should not reimplement this method, as it provides checks
    common for (probably) all child classes.

    :param u32_t start: index of the first requested block.
    :param u32_t cnt: number of blocks to read.
    """

    self.machine.DEBUG('%s.read_blocks: id=%s, start=%s, cnt=%s', self.__class__.__name__, self.sid, start, cnt)

    if (start + cnt) * BLOCK_SIZE > self.size:
      raise StorageAccessError('Out of bounds access: storage size {} is too small'.format(self.size))

    return self.do_read_blocks(start, cnt)

  def write_blocks(self, start, cnt, buff):
    """
    Write one or more blocks from internal buffer to device.

    Child classes should not reimplement this method, as it provides checks
    common for (probably) all child classes.

    :param u32_t start: index of the first requested block.
    :param u32_t cnt: number of blocks to write.
    """

    self.machine.DEBUG('%s.write_blocks: id=%s, start=%s, cnt=%s', self.__class__.__name__, self.sid, start, cnt)

    if (start + cnt) * BLOCK_SIZE > self.size:
      raise StorageAccessError('Out of bounds access: storage size {} is too small'.format(self.size))

    self.do_write_blocks(start, cnt, buff)

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

    self.machine.tenh('storage: file %s as storage #%i (%s)', self.filepath, self.sid, self.name)

  def halt(self):
    self.machine.DEBUG('FileBackedStorage.halt')

    self.file.flush()
    self.file.close()

  if six.PY2:
    def _read(self, cnt):
      return bytearray([ord(c) for c in self.file.read(cnt)])

    def _write(self, buff):
      self.file.write(''.join([chr(b) for b in buff]))

  else:
    def _read(self, cnt):
      return self.file.read(cnt)

    def _write(self, buff):
      self.file.write(bytes(buff))

  def do_read_blocks(self, start, cnt):
    self.machine.DEBUG('%s.do_read_blocks: start=%s, cnt=%s', self.__class__.__name__, start, cnt)

    self.file.seek(start * BLOCK_SIZE)

    return self._read(cnt * BLOCK_SIZE)

  def do_write_blocks(self, start, cnt, buff):
    self.machine.DEBUG('%s.do_write_blocks: start=%s, cnt=%s', self.__class__.__name__, start, cnt)

    self.file.seek(start * BLOCK_SIZE)
    self._write(buff)
    self.file.flush()

#
# Block IO subsystem
#

DEFAULT_IRQ = 0x02

BIO_RDY   = 0x00000001  #: Operation is completed, user can access data and/or request another operation
BIO_ERR   = 0x00000002  #: Error happened while performing the operation.
BIO_READ  = 0x00000004  #: Request data read - transfer data from storage to memory.
BIO_WRITE = 0x00000008  #: Request data write - transfer data from memory to storage.
BIO_BUSY  = 0x00000010  #: Data transfer in progress.
BIO_DMA   = 0x00000020  #: Request direct memory access - data will be transfered directly between storage and RAM..
BIO_SRST  = 0x00000040  #: Reset BIO.

BIO_USER  = BIO_READ | BIO_WRITE | BIO_DMA | BIO_SRST  #: Flags that user can set - others are read-only.

DEFAULT_MMIO_ADDRESS = 0x8400

class BlockIOPorts(enum.IntEnum):
  """
  MMIO ports, in form of offsets from a base MMIO address.
  """

  STATUS = 0x00  #: Status port - query BIO status, and submit commands by setting flags
  SID    = 0x04  #: ID of selected storage device
  BLOCK  = 0x08  #: Block ID
  COUNT  = 0x0C  #: Number of blocks
  ADDR   = 0x10  #: Address of a memory buffer
  DATA   = 0x14  #: Data port, for non-DMA access

class BlockIOMMIOMemoryPage(MMIOMemoryPage):
  def read_u32(self, offset):
    self.DEBUG('%s.read_u32: offset=%s', self.__class__.__name__, UINT8_FMT(offset))

    dev = self._device

    if offset == BlockIOPorts.STATUS:
      return dev._flags

    if offset == BlockIOPorts.DATA:
      return dev.read_data()

    self.WARN('%s.read_u32: attempt to read unhandled MMIO offset: offset=%s', self.__class__.__name__, UINT8_FMT(offset))
    return 0x00000000

  def write_u32(self, offset, value):
    self.DEBUG('%s.write_u32: offset=%s, value=%s', self.__class__.__name__, UINT8_FMT(offset), UINT32_FMT(value))

    value &= 0xFFFFFFFF
    dev = self._device

    if offset == BlockIOPorts.STATUS:
      dev.status_write(value)
      return

    if offset == BlockIOPorts.SID:
      dev.select_storage(value)
      return

    if offset == BlockIOPorts.BLOCK:
      dev._block = value
      return

    if offset == BlockIOPorts.COUNT:
      dev._count = value
      return

    if offset == BlockIOPorts.ADDR:
      dev._address = value
      return

    if offset == BlockIOPorts.DATA:
      dev.write_data(value)
      return

    self.WARN('%s.read_u32: attempt to write unhandled MMIO offset: offset=%s, value=%s', self.__class__.__name__, UINT8_FMT(offset), UINT32_FMT(value))

class BlockIO(Device):
  def __init__(self, machine, name, mmio_address = None, irq = None, *args, **kwargs):
    super(BlockIO, self).__init__(machine, 'bio', name, *args, **kwargs)

    self.DEBUG = self.machine.DEBUG

    self._mmio_address = mmio_address or DEFAULT_MMIO_ADDRESS
    self._mmio_page = None

    self.reset()

  @staticmethod
  def create_from_config(machine, config, section):
    return BlockIO(machine,
                   section,
                   mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS),
                   irq = config.getint(section, 'irq', DEFAULT_IRQ))

  def boot(self):
    self.DEBUG('%s.boot', self.__class__.__name__)

    self._mmio_page = BlockIOMMIOMemoryPage(self, self.machine.memory, addr_to_page(self._mmio_address))
    self.machine.memory.register_page(self._mmio_page)

    self.machine.tenh('BIO: controller on [%s] as %s', UINT32_FMT(self._mmio_address), self.name)

  def halt(self):
    self.DEBUG('%s.halt', self.__class__.__name__)

    self.machine.memory.unregister_page(self._mmio_page)

  def reset(self):
    self.DEBUG('%s.reset', self.__class__.__name__)

    self._buffer = None
    self._buffer_length = None
    self._buffer_index = None

    self._storage   = None
    self._device    = 0xFFFFFFFF
    self._flags     = BIO_RDY
    self._block     = 0x00000000
    self._count     = 0x00000000
    self._address   = 0x00000000

    self._dma = False
    self._busy = False

  def buff_to_memory(self, addr, buff):
    self.DEBUG('%s.buff_to_memory: addr=%s', self.__class__.__name__, UINT32_FMT(addr))

    for i in range(0, len(buff)):
      self.machine.memory.write_u8(addr + i, buff[i])

  def memory_to_buff(self, addr, length):
    self.DEBUG('%s.memory_to_buff: addr=%s, length=%s', self.__class__.__name__, UINT32_FMT(addr), length)

    return bytearray([self.machine.memory.read_u8(addr + i) for i in range(0, length)])

  def _flag_busy(self):
    """
    Signals BIO is running an operation: `BIO_BUSY` is set, and `BIO_RDY`
    is cleared.
    """

    self.DEBUG('%s._flag_busy', self.__class__.__name__)

    self._flags |=  BIO_BUSY
    self._flags &= ~BIO_RDY

  def _flag_finished(self):
    """
    Signals BIO is ready to accept new request: `BIO_RDY` is set, and `BIO_BUSY`
    is cleared.

    If there was an request running, it is finished now. User can queue another
    request, or access data in case read by the last request.
    """

    self.DEBUG('%s._flag_finished', self.__class__.__name__)

    self._flags &= ~BIO_BUSY
    self._flags |= BIO_RDY

  def _flag_error(self):
    """
    Signals BIO request failed: `BIO_ERR` is set, and both `BIO_RDY` and `BIO_BUSY`
    are cleared.
    """

    self.DEBUG('%s._flag_error', self.__class__.__name__)

    self._flags &= ~BIO_RDY
    self._flags &= ~BIO_BUSY
    self._flags |= BIO_ERR

  def status_write(self, value):
    """
    Handles writes to `STATUS` register. Starts the IO requested when
    `BIO_READ` or `BIO_WRITE` were set.
    """

    self.DEBUG('%s.status_write: value=%s', self.__class__.__name__, UINT32_FMT(value))

    value &= BIO_USER

    if value & BIO_SRST:
      self.DEBUG('%s.status_write: SRST', self.__class__.__name__)
      self.reset()

    if value & BIO_DMA:
      self.DEBUG('%s.status_write: DMA', self.__class__.__name__)
      self._dma = True

    if value & BIO_READ or value & BIO_WRITE:
      self.DEBUG('%s.status_write: IO', self.__class__.__name__)

      self._flag_busy()
      self._buffer_index = 0

      if self._storage is None:
        self._flag_error()
        return

      if value & BIO_READ:
        try:
          self._buffer = self._storage.read_blocks(self._block, self._count)

        except StorageAccessError:
          self._flag_error()

        else:
          if self._dma is True:
            self.buff_to_memory(self._address, self._buffer)

          self._flag_finished()

      else:
        if self._dma is True:
          self._buffer = self.memory_to_buff(self._address, self._count * BLOCK_SIZE)

        try:
          self._storage.write_blocks(self._block, self._count, self._buffer)

        except StorageAccessError:
          self._flag_error()

        else:
          self._flag_finished()

  def select_storage(self, sid):
    self.DEBUG('%s.select_storage: sid=%s', self.__class__.__name__, UINT32_FMT(sid))

    self._device_id = 0xFFFFFFFF
    self._storage = None

    try:
      self._storage = self.machine.get_storage_by_id(sid)
      self._device_id = sid

    except InvalidResourceError:
      self._flag_error()

  def read_data(self):
    if self._buffer_index == self._buffer_length:
      self._flag_error()
      return 0xFFFFFFFF

    i = self._buffer_index
    v = (self._buffer[i + 3] << 24) | (self._buffer[i + 2] << 16) | (self._buffer[i + 1] << 8) | self._buffer[i]

    self._buffer_index += 4
    return v

  def write_data(self, value):
    if self._buffer_index == self._buffer_length:
      self._flag_error()
      return

    i = self._buffer_index
    self._buffer[i]     =  value        & 0xFF
    self._buffer[i + 1] = (value >>  8) & 0xFF
    self._buffer[i + 1] = (value >> 16) & 0xFF
    self._buffer[i + 1] = (value >> 24) & 0xFF

    self._buffer_index += 4
