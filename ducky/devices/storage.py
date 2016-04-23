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
from . import Device, IRQList, IRQProvider, IOProvider
from ..mm import u32_t
from ..util import UINT16_FMT, UINT32_FMT, F

#: Size of block, in bytes.
BLOCK_SIZE = 1024

DEFAULT_PORT_RANGE = 0x400
DEFAULT_IRQ = IRQList.BIO

PORT_RANGE = 0x0005

BIO_RDY   = 0x00000001
BIO_ERR   = 0x00000002
BIO_READ  = 0x00000004
BIO_WRITE = 0x00000008
BIO_BUSY  = 0x00000010
BIO_DMA   = 0x00000020
BIO_SRST  = 0x00000040

BIO_USER  = BIO_READ | BIO_WRITE | BIO_DMA | BIO_SRST

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

class BlockIO(IRQProvider, IOProvider, Device):
  def __init__(self, machine, name, port = None, irq = None, *args, **kwargs):
    super(BlockIO, self).__init__(machine, 'bio', name, *args, **kwargs)

    self._device    = u32_t(0xFFFFFFFF)
    self._flags     = u32_t(BIO_RDY)
    self._block     = u32_t(0x00000000)
    self._count     = u32_t(0x00000000)
    self._address   = u32_t(0x00000000)

    self.port = port
    self.ports = list(range(port, port + PORT_RANGE))

    self.reset()

  @staticmethod
  def create_from_config(machine, config, section):
    return BlockIO(machine,
                   section,
                   port = config.getint(section, 'port', DEFAULT_PORT_RANGE),
                   irq = config.getint(section, 'irq', IRQList.TIMER))

  def boot(self):
    self.machine.DEBUG('BIO.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.tenh('BIO: controller on [%s] as %s', UINT16_FMT(self.port), self.name)

  def halt(self):
    for port in self.ports:
      self.machine.unregister_port(port)

  def reset(self):
    self.storage = None
    self.start = None
    self.count = None
    self.address = None

    self.buffer = None
    self.buffer_length = None
    self.buffer_index = None

    self.dma = False
    self.busy = False

    self._flags = u32_t(BIO_RDY)

  def buff_to_memory(self, addr, buff):
    self.machine.DEBUG('%s.buff_to_memory: addr=%s', self.__class__.__name__, UINT32_FMT(addr))

    for i in range(0, len(buff)):
      self.machine.memory.write_u8(addr + i, buff[i])

  def memory_to_buff(self, addr, length):
    self.machine.DEBUG('%s.memory_to_buff: addr=%s, length=%s', self.__class__.__name__, UINT32_FMT(addr), length)

    return bytearray([self.machine.memory.read_u8(addr + i) for i in range(0, length)])

  def __flag_busy(self):
    self._flags.value |=  BIO_BUSY
    self._flags.value &= ~BIO_RDY

  def __flag_finished(self):
    self._flags.value &= ~BIO_BUSY
    self._flags.value |= BIO_RDY

  def __flag_error(self):
    self._flags.value &= ~BIO_RDY
    self._flags.value &= ~BIO_BUSY
    self._flags.value |= BIO_ERR

  def read_u32(self, port):
    self.machine.DEBUG('%s.read_u32: port=%s', self.__class__.__name__, UINT16_FMT(port))

    if port not in self.ports:
      raise InvalidResourceError(F('Unhandled port: {port:S}', port = port))

    port -= self.port

    if port == 0x0000:
      return self._flags.value

    if port == 0x0005:
      if self.buffer_index == self.buffer_length:
        self._flags |= BIO_RDY
        return 0xFFFFFFFF

      v =  (self.buffer[self.buffer_index + 3] << 24) | (self.buffer[self.buffer_index + 2] << 16) | (self.buffer[self.buffer_index + 1] <<  8) |  self.buffer[self.buffer_index]

      self.buffer_index += 4
      return v

    raise InvalidResourceError(F('Write-only port: {port:S}', port = port + self.port))

  def write_u32(self, port, value):
    self.machine.DEBUG('%s.write_u32: port=%s, value=%s', self.__class__.__name__, UINT16_FMT(port), UINT32_FMT(value))

    if port not in self.ports:
      raise InvalidResourceError(F('Unhandled port: {port:S}', port = port))

    port -= self.port
    value &= 0xFFFFFFFF

    if port == 0x0000:
      value &= BIO_USER

      if value & BIO_SRST:
        self.machine.DEBUG('%s.write_u32: SRST', self.__class__.__name__)
        self.reset()

      if value & BIO_DMA:
        self.machine.DEBUG('%s.write_u32: DMA', self.__class__.__name__)
        self.dma = True

      if value & BIO_READ or value & BIO_WRITE:
        self.machine.DEBUG('%s.write_u32: IO', self.__class__.__name__)

        self.__flag_busy()

        self.buffer_index = 0

        if value & BIO_READ:
          try:
            self.buffer = self.storage.read_blocks(self._block.value, self._count.value)

          except StorageAccessError:
            self.__flag_error()

          else:
            if self.dma:
              self.buff_to_memory(self._address.value, self.buffer)
              self.__flag_finished()

        else:
          if self.dma is True:
            self.buffer = self.memory_to_buff(self._address.value, self._count.value * BLOCK_SIZE)

            try:
              self.storage.write_blocks(self._block.value, self._count.value, self.buffer)

            except StorageAccessError:
              self.__flag_error()

            else:
              self.__flag_finished()

      return

    if port == 0x0001:
      try:
        self.storage = self.machine.get_storage_by_id(value)
        self._device_id = value

      except InvalidResourceError:
        self.__flag_error()

      return

    if port == 0x0002:
      self._block.value = value
      return

    if port == 0x0003:
      self._count.value = value
      return

    if port == 0x0004:
      self._address.value = value
      return

    if port == 0x0005:
      if self.buffer_index == self.buffer_length:
        self._flags.value |= BIO_ERR
        return

      self.buffer[self.buffer_index]     =  value        & 0xFF
      self.buffer[self.buffer_index + 1] = (value >>  8) & 0xFF
      self.buffer[self.buffer_index + 1] = (value >> 16) & 0xFF
      self.buffer[self.buffer_index + 1] = (value >> 24) & 0xFF
      self.buffer_index += 4
      return

    raise InvalidResourceError(F('Read-only port: {port:S}', port = port + self.port))
