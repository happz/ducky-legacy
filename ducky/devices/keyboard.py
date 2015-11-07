"""
Keyboard controller - provides events for pressed and released keys.
"""

import enum
import io

from . import IRQProvider, IOProvider, Device, IRQList
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT

DEFAULT_PORT_RANGE = 0x100


class ControlMessages(enum.IntEnum):
  HALT = 1025

  CONTROL_MESSAGE_FIRST = 1024


def escape_char(c):
  return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')


class KeyboardController(IRQProvider, IOProvider, Device):
  def __init__(self, machine, name, streams = None, port = None, irq = None, *args, **kwargs):
    super(KeyboardController, self).__init__(machine, 'input', name, *args, **kwargs)

    self.streams = streams[:] if streams else []
    self.port = port or DEFAULT_PORT_RANGE
    self.ports = [port]
    self.irq = irq or IRQList.KEYBOARD

    self.input = None

    self.queue = []

  @staticmethod
  def create_from_config(machine, config, section):
    return KeyboardController(machine,
                              section,
                              streams = None,
                              port = config.getint(section, 'port', DEFAULT_PORT_RANGE),
                              irq = config.getint(section, 'irq', IRQList.KEYBOARD))

  def __repr__(self):
    return 'basic keyboard controller on [%s] as %s' % (', '.join([UINT16_FMT(port) for port in self.ports]), self.name)

  def enqueue_input(self, stream):
    self.machine.DEBUG('KeyboardController.enqueue_input: stream=%s', stream)

    if not stream.has_fd():
      raise InvalidResourceError('Keyboard controller requires input stream with fd support')

    self.streams.append(stream)

  def close_input(self):
    self.machine.DEBUG('KeyboardController.close_input: input=%s', self.input)

    if self.input is None:
      return

    self.machine.reactor.remove_fd(self.input.fd)

    self.input.close()
    self.input = None

  def open_input(self):
    self.machine.DEBUG('KeyboardController.open_input')

    self.close_input()

    if not self.streams:
      self.machine.DEBUG('no additional input streams')
      if not self.queue or self.queue[-1] != ControlMessages.HALT:
        self.machine.DEBUG('signal halt')
        self.queue.append(ControlMessages.HALT)
      return

    self.input = self.streams.pop(0)
    self.machine.DEBUG('KeyboardController.input=%s', self.input)

    self.machine.reactor.add_fd(self.input.fd, on_read = self.handle_raw_input, on_error = self.handle_input_error)

  def boot(self):
    self.machine.DEBUG('KeyboardController.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.open_input()

    self.machine.INFO('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('KeyboardController.halt')

    for port in self.ports:
      self.machine.unregister_port(port)

    self.close_input()

  def handle_input_error(self):
    self.machine.DEBUG('KeyboardController.handle_input_error')

    self.open_input()

  def handle_raw_input(self):
    self.machine.DEBUG('KeyboardController.handle_raw_input')

    assert self.input is not False

    buff = self.input.read(size = io.DEFAULT_BUFFER_SIZE)
    self.machine.DEBUG('KeyboardController.handle_raw_input: buff=%s (%s)', buff, type(buff))

    if buff is None:
      self.machine.DEBUG('KeyboardController.handle_raw_input: nothing to do, no input')
      return

    if not buff:
      # EOF
      self.open_input()
      return

    self.machine.DEBUG('KeyboardController.handle_raw_input: adding %i chars', len(buff))

    self.queue += buff

    self.machine.DEBUG('KeyboardController.handle_raw_input: queue now has %i bytes', len(self.queue))

    self.machine.trigger_irq(self)

  def __read_char(self):
    self.machine.DEBUG('KeyboardController.__read_char')

    while True:
      try:
        b = self.queue.pop(0)

      except IndexError:
        self.machine.DEBUG('KeyboardController.__read_char: no available chars in queue')
        return None

      self.machine.DEBUG('KeyboardController.__read_char: queue now has %i bytes', len(self.queue))

      if b == ControlMessages.HALT:
        self.machine.DEBUG('KeyboardController.__read_char: planned halt, execute')
        self.machine.halt()

        return None

      break

    self.machine.DEBUG('KeyboardController.__read_char: c=%s ()', b)

    return b

  def read_u8(self, port):
    self.machine.DEBUG('KeyboardController.read_u8: port=%s', UINT16_FMT(port))

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s', UINT16_FMT(port))

    b = self.__read_char()
    if not b:
      self.machine.DEBUG('KeyboardController.read_u8: empty input, signal it downstream')
      return 0xFF

    self.machine.DEBUG('KeyboardController.read_u8: input byte is %i', b)

    return b
