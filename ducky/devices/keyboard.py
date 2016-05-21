"""
Keyboard controller - provides events for pressed and released keys.
"""

import enum
import io

from . import IRQProvider, DeviceFrontend, DeviceBackend, IRQList, MMIOMemoryPage
from ..errors import InvalidResourceError
from ..mm import UINT8_FMT, addr_to_page, UINT32_FMT, u32_t
from ..hdt import HDTEntry_Device

DEFAULT_IRQ = 0x01
DEFAULT_MMIO_ADDRESS = 0x8000

class KeyboardPorts(enum.IntEnum):
  STATUS = 0x00
  DATA   = 0x01

  LAST   = 0x01

class HDTEntry_Keyboard(HDTEntry_Device):
  _fields_ = HDTEntry_Device.ENTRY_HEADER + [
    ('mmio_address', u32_t)
  ]

  def __init__(self, logger, config, section):
    super(HDTEntry_Keyboard, self).__init__(logger, section, 'Virtual keyboard controller')

    self.mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS)

    logger.debug('%s: mmio-address=%s', self.__class__.__name__, UINT32_FMT(self.mmio_address))

class KeyboardMMIOMemoryPage(MMIOMemoryPage):
  def read_u8(self, offset):
    self.DEBUG('%s.read_u8: offset=%s', self.__class__.__name__, UINT8_FMT(offset))

    if offset == KeyboardPorts.STATUS:
      return 0x00

    if offset == KeyboardPorts.DATA:
      b = self._device._read_char()
      if not b:
        self.DEBUG('%s.get: empty input, signal it downstream', self.__class__.__name__)
        return 0xFF

      self.DEBUG('%s.get: input byte is %i', self.__class__.__name__, b)
      return b

    self.WARN('%s.read_u8: attempt to read raw offset: offset=%s', self.__class__.__name__, UINT8_FMT(offset))
    return 0x00

class ControlMessages(enum.IntEnum):
  HALT = 1025

  CONTROL_MESSAGE_FIRST = 1024

class Frontend(DeviceFrontend):
  def __init__(self, machine, name):
    super(Frontend, self).__init__(machine, 'input', name)

    self._comm_queue = machine.comm_channel.get_queue(name)
    self._streams = []
    self._stream = None

    self.backend = machine.get_device_by_name(name)

  @staticmethod
  def create_from_config(machine, config, section):
    slave = config.get(section, 'slave', default = section)

    return Frontend(machine, slave)

  def boot(self):
    super(Frontend, self).boot()

    self._open_input()
    self.backend.boot()

  def halt(self):
    self._close_input()
    self.backend.halt()

    super(Frontend, self).halt()

  def enqueue_stream(self, stream):
    self.machine.DEBUG('%s.enqueue_input: stream=%s', self.__class__.__name__, stream)

    if not stream.has_poll_support():
      raise InvalidResourceError('Keyboard stream must support polling')

    self._streams.append(stream)

  def _close_input(self):
    self.machine.DEBUG('%s._close_input: input=%s', self.__class__.__name__, self._stream)

    if self._stream is None:
      return

    self._stream.unregister_with_reactor(self.machine.reactor)
    self._stream = None

  def _open_input(self):
    self.machine.DEBUG('%s._open_input', self.__class__.__name__)

    self._close_input()

    if not self._streams:
      self.machine.DEBUG('%s._open_input: no additional input streams', self.__class__.__name__)
      self._comm_queue.write_in(ControlMessages.HALT)

      # if not self.queue or self.queue[-1] != ControlMessages.HALT:
      #   self.machine.DEBUG('signal halt')
      #   self.queue.append(ControlMessages.HALT)
      return

    self._stream = self._streams.pop(0)
    self.machine.DEBUG('%s._open_input: stream=%r', self.__class__.__name__, self._stream)

    self._stream.register_with_reactor(self.machine.reactor, on_read = self._handle_raw_input, on_error = self._handle_input_error)

  def _handle_input_error(self):
    self.machine.DEBUG('%s._handle_input_error')

    self._open_input()

  def _handle_raw_input(self):
    self.machine.DEBUG('%s._handle_raw_input', self.__class__.__name__)

    assert self._stream is not False

    buff = self._stream.read(size = io.DEFAULT_BUFFER_SIZE)
    self.machine.DEBUG('%s._handle_raw_input: buff=%s (%s)', self.__class__.__name__, buff, type(buff))

    if buff is None:
      self.machine.DEBUG('%s._handle_raw_input: nothing to do, no input', self.__class__.__name__)
      return

    if not buff:
      # EOF
      self._open_input()
      return

    self.machine.DEBUG('%s._handle_raw_input: adding %i chars', self.__class__.__name__, len(buff))

    self._comm_queue.write_in(buff)

    self.machine.trigger_irq(self.backend)

class Backend(IRQProvider, DeviceBackend):
  def __init__(self, machine, name, mmio_address = None, irq = None):
    super(Backend, self).__init__(machine, 'input', name)

    self._mmio_address = mmio_address or DEFAULT_MMIO_ADDRESS
    self._mmio_page = None
    self.irq = irq or DEFAULT_IRQ

    self._comm_queue = machine.comm_channel.create_queue(name)
    self._key_queue = []

  @staticmethod
  def create_from_config(machine, config, section):
    return Backend(machine, section,
                   mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS),
                   irq = config.getint(section, 'irq', IRQList.KEYBOARD))

  @staticmethod
  def create_hdt_entries(logger, config, section):
    return [HDTEntry_Keyboard(logger, config, section)]

  def __repr__(self):
    return 'basic keyboard controller on [%s] as %s' % (UINT32_FMT(self._mmio_address), self.name)

  def boot(self):
    self.machine.DEBUG('%s.boot', self.__class__.__name__)

    self._mmio_page = KeyboardMMIOMemoryPage(self, self.machine.memory, addr_to_page(self._mmio_address))
    self.machine.memory.register_page(self._mmio_page)

    self.machine.tenh('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('%s.halt', self.__class__.__name__)

    self.machine.memory.unregister_page(self._mmio_page)

  def _process_input_event(self, e):
    self.machine.DEBUG('%s.__process_input_event: e=%r', self.__class__.__name__, e)

    if isinstance(e, (list, bytearray, bytes)):
      for key in e:
        self._key_queue.append(key)

    elif isinstance(e, ControlMessages):
      self._key_queue.append(e)

    else:
      raise InvalidResourceError('Unknown message: e=%s, type=%s' % (e, type(e)))

  def _process_input_events(self):
    self.machine.DEBUG('%s.__process_input_events', self.__class__.__name__)

    while True:
      e = self._comm_queue.read_in()
      if e is None:
        return

      self._process_input_event(e)

  def _read_char(self):
    self.machine.DEBUG('%s._read_char', self.__class__.__name__)

    def __do_read_char():
      try:
        b = self._key_queue.pop(0)

      except IndexError:
        self.machine.DEBUG('%s._read_char: no available chars in queue', self.__class__.__name__)
        return None

      return b

    def __process_char(b):
      self.machine.DEBUG('%s._read_char: queue now has %i bytes', self.__class__.__name__, len(self._key_queue))

      if b == ControlMessages.HALT:
        self.machine.DEBUG('%s._read_char: planned halt, execute', self.__class__.__name__)
        self.machine.halt()

        return None

      self.machine.DEBUG('%s._read_char: c=%s ()', self.__class__.__name__, b)

      return b

    b = __do_read_char()
    if b is not None:
      return __process_char(b)

    self._process_input_events()

    b = __do_read_char()
    if b is None:
      return None

    return __process_char(b)
