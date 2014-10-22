import sys

try:
  import termios
except ImportError:
  print >> sys.stderr, 'termios not available, console simlation will be limited'
  termios = None

import io

from mm import UInt8

class ConsoleIOHandler(io.IOHandler):
  def __init__(self, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.__buffer = []

    self.is_privileged = True

    self.cpu.register_port(0x100, self)

  def add_to_buffer(self, s):
    for c in s:
      self.__buffer.append(ord(c))

  def read_u8_256(self):
    if len(self.__buffer) <= 0:
      return 0xFF

    return UInt8(self.__buffer.pop(0))

  def write_u8_256(self, value):
    sys.stdout.write('%s' % chr(value.u8))
