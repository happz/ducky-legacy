import sys

try:
  import termios
except ImportError:
  print >> sys.stderr, 'termios not available, console simlation will be limited'
  termios = None

import io

from util import debug, warn
from mm import UInt8, UINT8_FMT

try:
  import termios
except ImportError:
  warn('termios not available, console simlation will be limited')
  termios = None

class ConsoleIOHandler(io.IOHandler):
  def __init__(self, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.__buffer = []

    self.is_privileged = True

    self.termios_attrs = None

  def boot(self):
    if not termios:
      return

    if self.termios_attrs:
      return

    self.termios_attrs = termios.tcgetattr(sys.stdin)

    termios_attrs = termios.tcgetattr(sys.stdin)
    termios_attrs[3] &= (~termios.ICANON)
    termios.tcsetattr(sys.stdin, termios.TCSANOW, termios_attrs)

  def halt(self):
    if not termios:
      return

    termios.tcsetattr(sys.stdin, termios.TCSANOW, self.termios_attrs)
    self.termios_attrs = None

  def add_to_buffer(self, s):
    for c in s:
      self.__buffer.append(ord(c))

  def read_u8_256(self):
    if len(self.__buffer) <= 0:
      return 0xFF

    return UInt8(self.__buffer.pop(0))

  def write_u8_256(self, value):
    debug('conio.write_u8_256: value=%s' % UINT8_FMT(value.u8))

    sys.stdout.write('%s' % chr(value.u8))

  def write_u8_257(self, value):
    debug('conio.write_u8_257: value=%s' % UINT8_FMT(value.u8))

    sys.stderr.write('%s' % chr(value.u8))
