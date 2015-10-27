import os
import sys

from . import IOProvider, Device
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT
from ..util import isfile

DEFAULT_PORT_RANGE = 0x200

def escape_char(c):
  return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')

class TTY(IOProvider, Device):
  def __init__(self, machine, name, stream = None, port = None, *args, **kwargs):
    super(TTY, self).__init__(machine, 'output', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = range(port, port + 0x0001)

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

    if isfile(stream):
      self.machine.DEBUG('  stream is opened file %s', stream.name)

      self.output = stream
      self.output_fd = stream.fileno()

    elif hasattr(stream, 'fileno'):
      self.machine.DEBUG('  stream has fileno()')

      self.output = stream
      self.output_fd = stream.fileno()

    elif isinstance(stream, int):
      self.machine.DEBUG('  stream is raw file descriptor')

      self.output = None
      self.output_fd = stream

    elif stream == '<stdout>':
      self.machine.DEBUG('  stream is stdout')

      self.output = sys.stdout
      self.output_fd = sys.stdout.fileno()

    elif stream is None:
      self.machine.DEBUG('  stream is dummy, none')

      self.output = None
      self.output_fd = None

    else:
      self.machine.WARN('Unknown output stream type: stream=%s, class=%s', stream, type(stream))

      self.output = None
      self.output_fd = None

  def __write_char(self, c):
    self.machine.DEBUG('TTY.__write_char: c=%s (%s)', c, escape_char(c))

    try:
      s = chr(c)

      os.write(self.output_fd, s)

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
