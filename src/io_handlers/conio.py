import fcntl
import select
import sys

try:
  import termios
except ImportError:
  print >> sys.stderr, 'termios not available, console simlation will be limited'
  termios = None

import io_handlers

from util import debug, warn
from mm import UInt8, UINT8_FMT

class ConsoleIOHandler(io_handlers.IOHandler):
  def __init__(self, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.__buffer = []

    self.is_privileged = True

    self.termios_attrs = None
    self.fcntl_flags = None

  def boot(self):
    if self.termios_attrs:
      return

    if termios:
      self.termios_attrs = termios.tcgetattr(sys.stdin)

      termios_attrs = termios.tcgetattr(sys.stdin)
      termios_attrs[3] &= (~termios.ICANON)
      termios.tcsetattr(sys.stdin, termios.TCSANOW, termios_attrs)

    if self.fcntl_flags:
      self.fcntl_flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
      fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, self.fcntl_flags | os.O_NONBLOCK)

  def halt(self):
    if self.termios_attrs:
      #termios.tcsetattr(sys.stdin, termios.TCSANOW, self.termios_attrs)
      self.termios_attrs = None

    if self.fcntl_flags:
      fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, self.fcntl_flags)

  def __read_char(self):
    debug('conio.__read_char')

    if sys.stdin not in select.select([sys.stdin], [], [], 0)[0]:
      debug('conio.__read_char: select claims no input available')
      return None

    try:
      debug('conio.__read_char: reading byte from input')
      return sys.stdin.read(1)

    except IOError, e:
      error('conio.__read_char: %s' % e)
      return None

  def read_u8_256(self):
    debug('conio.read_u8_256')

    c = self.__read_char()
    if not c:
      debug('conio.read_u8_256: empty input, signal it downstream')
      return UInt8(0xFF)

    debug('conio.read_u8_256: input byte is %i' % ord(c))

    return UInt8(ord(c))

  def write_u8_256(self, value):
    debug('conio.write_u8_256: value=%s' % UINT8_FMT(value.u8))

    sys.stdout.write('%s' % chr(value.u8))

  def write_u8_257(self, value):
    debug('conio.write_u8_257: value=%s' % UINT8_FMT(value.u8))

    sys.stderr.write('%s' % chr(value.u8))
