import fcntl
import os
import pty
import pytty
import select
import sys
import termios

import io_handlers

import util

from util import debug, warn
from mm import UInt8, UINT8_FMT
from util import info, error

CR = UInt8(ord('\r'))
LF = UInt8(ord('\n'))

class ConsoleIOHandler(io_handlers.IOHandler):
  def __init__(self, f_in, f_out, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.is_privileged = True

    self.pttys = None
    self.termios_attrs = None

    self.echo = True
    self.crlf = True

    self.terminal_device = None
    self.input = f_in
    self.output = f_out
    self.input_fd = None

    self.booted = False

  def get_terminal_dev(self):
    return self.terminal_device
    return os.ttyname(self.pttys[1])

  def boot(self):
    if self.booted:
      return

    if self.input or self.output:
      if self.input:
        self.input = open(self.input, 'rb')
        self.input_fd = self.input.fileno()

      else:
        warn('No console input stream sepcified')

      self.output = open(self.output or '/dev/null', 'wb')

      self.terminal_device = self.output.name

    else:
      self.pttys = pty.openpty()

      self.input = self.output = pytty.TTY(self.pttys[0])
      self.input_fd = self.pttys[0]

      self.terminal_device = os.ttyname(self.pttys[1])

      def cmd_conio_pty(console, cmd):
        """
        Print path to guest terminal pty
        """

        info('Guest terminal available at %s' % self.get_terminal_dev())

      util.CONSOLE.__class__.register_command('conio_pty', cmd_conio_pty)

    self.booted = True

  def halt(self):
    if not self.booted:
      return

    if self.pttys:
      try:
        os.close(self.pttys[1])
        os.close(self.pttys[0])

        self.input = self.output = None
      except:
        pass

      self.input = self.output = None

    if self.input:
      self.input.close()

    if self.output:
      self.output.close()

  def check_available_input(self):
    if not self.input_fd:
      return False

    try:
      r_read, r_write, r_exc = select.select([self.input_fd], [], [], 0)
      return self.input_fd in r_read

    except:
      return False

  def __read_char(self):
    debug('conio.__read_char')

    if not self.check_available_input():
      debug('conio.__read_char: select claims no input available')
      return None

    try:
      debug('conio.__read_char: reading byte from input')
      return self.input.read(1)

    except IOError, e:
      error('conio.__read_char: %s' % e)
      return None

  def __write_char(self, c):
    debug('conio.__write_char: c=%s' % UINT8_FMT(c))

    try:
      self.output.write('%s' % chr(c.u8))
      self.output.flush()

    except IOError, e:
      error('Exception raised during console write: %s' % str(e))

  def read_u8_256(self):
    debug('conio.read_u8_256')

    c = self.__read_char()
    if not c:
      debug('conio.read_u8_256: empty input, signal it downstream')
      return UInt8(0xFF)

    debug('conio.read_u8_256: input byte is %i' % ord(c))

    c = UInt8(ord(c))

    if self.echo:
      self.write_u8_256(c)

      if self.crlf and c.u8 == CR.u8:
        self.write_u8_256(LF)

    return c

  def write_u8_256(self, value):
    debug('conio.write_u8_256: value=%s' % UINT8_FMT(value.u8))

    self.__write_char(value)

  def write_u8_257(self, value):
    debug('conio.write_u8_257: value=%s' % UINT8_FMT(value.u8))

    self.__write_char(value)

  def writeln(self, line):
    debug('conio.writeln: line=%s' % line)

    for c in line:
      self.__write_char(UInt8(ord(c)))

    self.__write_char(CR)
    self.__write_char(LF)
