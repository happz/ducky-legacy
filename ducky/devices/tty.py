import sys

from . import IOProvider, Device
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT, UINT8_FMT

DEFAULT_PORT_RANGE = 0x200

def escape_char(c):
  return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')

class TTY(IOProvider, Device):
  def __init__(self, machine, name, stream = None, port = None, *args, **kwargs):
    super(TTY, self).__init__(machine, 'output', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = [port]

    self.output = None

    if stream is not None:
      self.set_output(stream)

  @staticmethod
  def create_from_config(machine, config, section):
    return TTY(machine,
               section,
               port = config.getint(section, 'port', DEFAULT_PORT_RANGE))

  def __repr__(self):
    return 'basic tty on [%s] as %s' % (', '.join([UINT16_FMT(port) for port in self.ports]), self.name)

  def set_output(self, stream):
    self.machine.DEBUG('TTY.set_output: stream=%s', stream)

    self.output = stream

  def write_u8(self, port, value):
    self.machine.DEBUG('TTY.write_u8: port=%s, value=%s', UINT16_FMT(port), UINT8_FMT(value))

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s', UINT16_FMT(port))

    self.output.write([value])

  def boot(self):
    self.machine.DEBUG('TTY.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.DEBUG('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('TTY.halt')

    for port in self.ports:
      self.machine.unregister_port(port)

    if self.output:
      if self.output != sys.stdout:
        self.output.close()

      self.output = None
      self.output_fd = None
