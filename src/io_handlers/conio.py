import fcntl
import os
import pty
import pytty
import select
import sys
import termios

import io_handlers

from util import debug, warn
from mm import UInt8, UINT8_FMT
from util import info, error

CR = UInt8(ord('\r'))
LF = UInt8(ord('\n'))

class ConsoleIOHandler(io_handlers.IOHandler):
  def __init__(self, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.is_privileged = True

    self.pttys = None
    self.termios_attrs = None

    self.echo = True
    self.crlf = True

  def boot(self):
    if self.pttys:
      return

    self.pttys = pty.openpty()

    self.master = pytty.TTY(self.pttys[0])
    self.slave  = pytty.TTY(self.pttys[1])

    info('Guest terminal opened available at %s' % os.ttyname(self.pttys[1]))
    raw_input('Press Enter when you have connected console to guest output')

  def halt(self):
    if not self.pttys:
      return

    try:
      os.close(self.pttys[1])
      os.close(self.pttys[0])

    except:
      pass

  def check_available_input(self):
    master_fd = self.pttys[0]

    try:
      r_read, r_write, r_exc = select.select([master_fd], [], [], 0)
      return master_fd in r_read

    except:
      return False

  def __read_char(self):
    debug('conio.__read_char')

    if not self.check_available_input():
      debug('conio.__read_char: select claims no input available')
      return None

    try:
      debug('conio.__read_char: reading byte from input')
      return self.master.read(1)

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

    c = UInt8(ord(c))

    if self.echo:
      self.write_u8_256(c)

      if self.crlf and c.u8 == CR.u8:
        self.write_u8_256(LF)

    return c

  def write_u8_256(self, value):
    debug('conio.write_u8_256: value=%s' % UINT8_FMT(value.u8))

    try:
      self.master.write('%s' % chr(value.u8))
      self.master.flush()

    except IOError, e:
      error('Exception raised during console write: %s' % str(e))

  def write_u8_257(self, value):
    debug('conio.write_u8_257: value=%s' % UINT8_FMT(value.u8))

    try:
      self.master.write('%s' % chr(value.u8))
      self.master.flush()

    except IOError, e:
      error('Exception raised during console write: %s' % str(e))

  def writeln(self, line):
    debug('conio.writeln: line=%s' % line)

    for c in line:
      self.write_u8_256(UInt8(ord(c)))

    self.write_u8_256(CR)
    self.write_u8_256(LF)
