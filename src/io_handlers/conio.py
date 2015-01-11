import enum
import fcntl
import os
import pty
import pytty
import Queue
import select
import sys
import termios
import types

import io_handlers

import util

from util import debug, warn
from mm import UInt8, UINT8_FMT
from util import info, warn, error

CR = UInt8(ord('\r'))
LF = UInt8(ord('\n'))

class ControlMessages(enum.IntEnum):
  CRLF_ON  = 1024
  CRLF_OFF = 1025

  CONTROL_MESSAGE_FIRST = 1024

class ConsoleIOHandler(io_handlers.IOHandler):
  def __init__(self, f_in, f_out, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.is_privileged = True

    self.pttys = None
    self.termios_attrs = None

    self.echo = True
    self.crlf = False

    self.input_streams = f_in or []
    self.output_streams = f_out

    self.terminal_device = None
    self.input = None
    self.output = None
    self.input_fd = None

    self.queue = Queue.Queue()

    self.booted = False

  def get_terminal_dev(self):
    return self.terminal_device

  def __open_input_stream(self):
    debug('conio.__open_input_stream')

    if self.input:
      debug('conio.__open_input_stream: closing existing input stream')

      self.input.close()

      self.input = None
      self.input_fd = None

    stream = self.input_streams.pop(0)

    if type(stream) == pytty.TTY:
      self.input = stream
      self.input_fd = self.pttys[0]
      self.queue.put(ControlMessages.CRLF_ON)

    elif type(stream) == types.StringType:
      self.input = open(stream, 'rb')
      self.input_fd = self.input.fileno()
      self.queue.put(ControlMessages.CRLF_OFF)

    else:
      warn('__open_input_stream: Unknown input stream type: %s of type %s', stream, type(stream))
      self.__open_input_stream()

    debug('conio.__open_input_stream: stream=%s, input_fd=%s', self.input, self.input_fd)

  def boot(self):
    if self.booted:
      return

    self.pttys = pty.openpty()

    self.input_streams.append(pytty.TTY(self.pttys[0]))

    if self.output_streams:
      self.output = open(self.output_streams, 'wb')

    else:
      self.output = pytty.TTY(self.pttys[0])

    self.terminal_device = os.ttyname(self.pttys[1])

    def cmd_conio_pty(console, cmd):
      """
      Print path to guest terminal pty
      """

      info('Guest terminal available at %s', self.get_terminal_dev())

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
      self.__open_input_stream()

    #debug('conio.check_available_input: input_fd=%s' % self.input_fd)

    try:
      r_read, r_write, r_exc = select.select([self.input_fd], [], [])

      #debug('conio.check_available_input: r_read=%s, r_write=%s, r_exc=%s' % (r_read, r_write, r_exc))
      return self.input_fd in r_read

    except Exception, e:
      debug('conio.check_available_input: exception happened: e=%s', type(e))
      return False

  def read_raw_input(self):
    while True:
      if not self.check_available_input():
        debug('conio.read_input: no input available')
        return

      debug('conio.read_input: reading byte from input')

      try:
        s = self.input.read()

        if type(s) == types.StringType and len(s) == 0:
          # EOF
          self.__open_input_stream()
          continue

        for c in s:
          self.queue.put(c)

      except IOError, e:
        error('conio.__read_char: %s', e)

      return

  def __escape_char(self, c):
    return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')

  def __read_char(self):
    while True:
      if self.queue.empty():
        debug('conio.__read_char: select claims no input available')
        return None

      c = self.queue.get_nowait()

      if type(c) == ControlMessages:
        if c == ControlMessages.CRLF_ON:
          self.crlf = True

        elif c == ControlMessages.CRLF_OFF:
          self.crlf = False

        continue

      break

    c = UInt8(ord(c))

    debug('conio.__read_char: c=%s (%s)', c, self.__escape_char(c.u8))

    return c

  def __write_char(self, c):
    debug('conio.__write_char: c=%s (%s)', c, self.__escape_char(c.u8))

    try:
      self.output.write('%s' % chr(c.u8))
      self.output.flush()

    except IOError, e:
      error('Exception raised during console write: %s', str(e))

  def read_u8_256(self):
    debug('conio.read_u8_256')

    c = self.__read_char()
    if not c:
      debug('conio.read_u8_256: empty input, signal it downstream')
      return UInt8(0xFF)

    debug('conio.read_u8_256: input byte is %s', c)

    if self.echo:
      self.write_u8_256(c)

    if self.crlf == True and c.u8 == CR.u8:
      self.write_u8_256(LF)

    return c

  def write_u8_256(self, value):
    debug('conio.write_u8_256: value=%s', value)

    self.__write_char(value)

  def write_u8_257(self, value):
    debug('conio.write_u8_257: value=%s', value)

    self.__write_char(value)

  def writeln(self, line):
    debug('conio.writeln: line=%s', line)

    for c in line:
      self.__write_char(UInt8(ord(c)))

    self.__write_char(CR)
    self.__write_char(LF)
