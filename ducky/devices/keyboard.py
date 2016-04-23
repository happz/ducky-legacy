"""
Keyboard controller - provides events for pressed and released keys.
"""

import enum
import io

from . import IRQProvider, IOProvider, DeviceFrontend, DeviceBackend, IRQList
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT

DEFAULT_IRQ = 0x01
DEFAULT_PORT_RANGE = 0x100


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

class Backend(IRQProvider, IOProvider, DeviceBackend):
  def __init__(self, machine, name, port = None, irq = None):
    super(Backend, self).__init__(machine, 'input', name)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = [port]
    self.irq = irq or DEFAULT_IRQ

    self._comm_queue = machine.comm_channel.create_queue(name)
    self._key_queue = []

  @staticmethod
  def create_from_config(machine, config, section):
    return Backend(machine, section,
                   port = config.getint(section, 'port', DEFAULT_PORT_RANGE),
                   irq = config.getint(section, 'irq', IRQList.KEYBOARD))

  def __repr__(self):
    return 'basic keyboard controller on [%s] as %s' % (', '.join([UINT16_FMT(port) for port in self.ports]), self.name)

  def boot(self):
    self.machine.DEBUG('%s.boot', self.__class__.__name__)

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.tenh('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('%s.halt', self.__class__.__name__)

    for port in self.ports:
      self.machine.unregister_port(port)

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

  def read_u8(self, port):
    self.machine.DEBUG('%s.read_u8: port=%s', self.__class__.__name__, UINT16_FMT(port))

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s' % UINT16_FMT(port))

    b = self._read_char()
    if not b:
      self.machine.DEBUG('%s.read_u8: empty input, signal it downstream', self.__class__.__name__)
      return 0xFF

    self.machine.DEBUG('%s.read_u8: input byte is %i', self.__class__.__name__, b)

    return b
