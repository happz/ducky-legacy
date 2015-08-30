import sys

from . import IOProvider, Device
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT

DEFAULT_PORT_RANGE = 0x200

class TTY(IOProvider, Device):
  def __init__(self, machine, name, stream = None, stream_fd = None, port = None, *args, **kwargs):
    super(TTY, self).__init__(machine, 'output', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = range(port, port + 0x0001)

    self.set_output(stream, stream_fd = stream_fd)

  @classmethod
  def create_from_config(self, machine, config, section):
    return TTY(machine,
               section,
               port = config.getint(section, 'port', DEFAULT_PORT_RANGE))

  def __repr__(self):
    return 'basic tty on [%s] as %s' % (', '.join([UINT16_FMT(port) for port in self.ports]), self.name)

  def set_output(self, stream, stream_fd = None):
    self.machine.DEBUG('TTY.set_output: stream=%s, stream_fd=%s', stream, stream_fd)

    self.output = stream
    self.output_fd = stream_fd or (stream.fileno() if stream else None)

  def __escape_char(self, c):
    return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')

  def __write_char(self, c):
    self.machine.DEBUG('TTY.__write_char: c=%s (%s)', c, self.__escape_char(c))

    try:
      s = chr(c)

      self.output.write(s)

    except IOError:
      self.machine.EXCEPTION('Exception raised during terminal output')

  def write_u8(self, port, value):
    self.machine.DEBUG('TTY.write_u8: port=%s, value=%s', UINT16_FMT(port), value)

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s', UINT16_FMT(port))

    self.__write_char(value)

  def boot(self):
    self.machine.DEBUG('TTY.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.INFO('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('TTY.halt')

    for port in self.ports:
      self.machine.unregister_port(port)

    if self.output:
      if self.output != sys.stdout:
        self.output.close()

      self.output = None
      self.output_fd = None
