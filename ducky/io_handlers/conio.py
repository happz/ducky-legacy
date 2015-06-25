import enum
import os
import pty
import pytty
import select
import sys
import types

from .. import io_handlers
from .. import util

from ..cpu.registers import Registers
from ..util import debug, info, warn, error, exception
from ..console import WHITE
from ..irq import InterruptList
from ..irq.virtual import VirtualInterrupt, VIRTUAL_INTERRUPTS

CR = ord('\r')
LF = ord('\n')

class ControlMessages(enum.IntEnum):
  CRLF_ON   = 1024
  CRLF_OFF  = 1025
  ECHO_ON   = 1026
  ECHO_OFF  = 1027
  FLUSH_ON  = 1028
  FLUSH_OFF = 1029
  HALT      = 1030

  CONTROL_MESSAGE_FIRST = 1024

class ConsoleIOHandler(io_handlers.IOHandler):
  CTRL_HALT = ControlMessages.HALT

  def __init__(self, f_in, f_out, *args, **kwargs):
    super(ConsoleIOHandler, self).__init__(*args, **kwargs)

    self.is_privileged = True

    self.open_console = True

    self.pttys = None
    self.termios_attrs = None

    self.stdout_echo = False
    self.echo = True
    self.crlf = False
    self.highlight = False

    self.input_streams = f_in or []
    self.output_streams = f_out

    self.terminal_device = None
    self.input = None
    self.output = None
    self.input_fd = None

    self.immediate_flush = False

    self.queue = []

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

    # In case input_streams are empty, there is no ptty console,
    # just halt VM - no other input wil ever come
    if not self.input_streams:
      debug('conio.__open_input_stream: no additional input streams')
      if self.queue[-1] != ConsoleIOHandler.CTRL_HALT:
        debug('conio.__open_input_stream: plan halt')
        self.queue.append(ConsoleIOHandler.CTRL_HALT)
      return

    stream = self.input_streams.pop(0)

    if type(stream) == pytty.TTY:
      debug('conio.__open_input_stream: console attached')

      self.input = stream
      self.input_fd = self.pttys[0]

      l = [ControlMessages.CRLF_ON, ControlMessages.ECHO_ON, ControlMessages.FLUSH_ON]
      if self.queue[-3:] != l:
        self.queue += l

    elif isinstance(stream, types.StringType):
      debug('conio.__open_input_stream: input file attached')

      self.input = open(stream, 'rb')
      self.input_fd = self.input.fileno()

      l = [ControlMessages.CRLF_OFF, ControlMessages.ECHO_ON if self.echo is True else ControlMessages.ECHO_OFF, ControlMessages.FLUSH_OFF]
      if self.queue[-3:] != l:
        self.queue += l

    else:
      warn('__open_input_stream: Unknown input stream type: %s of type %s', stream, type(stream))
      self.__open_input_stream()

    self.flush_output()

    debug('conio.__open_input_stream: stream=%s, input_fd=%s', self.input, self.input_fd)

  def do_flush_output(self):
    if not self.output or not hasattr(self.output, 'flush') or (hasattr(self.output, 'closed') and self.output.closed is not False):
      return

    self.output.flush()

  def flush_output(self):
    # if not self.immediate_flush:
    #   return

    self.do_flush_output()

  def boot(self):
    if self.booted:
      return

    if self.open_console:
      self.pttys = pty.openpty()

      ptty = pytty.TTY(self.pttys[0])
      ptty.baud = 115200
      self.input_streams.append(ptty)

    self.queue.append(ControlMessages.ECHO_ON if self.echo is True else ControlMessages.ECHO_OFF)
    self.queue.append(ControlMessages.FLUSH_OFF)

    if self.output_streams:
      self.output = open(self.output_streams, 'wb')

    else:
      if not self.open_console:
        warn('conio: you have no access to VM output')

      else:
        self.output = pytty.TTY(self.pttys[0])
        self.queue.append(ControlMessages.ECHO_ON)
        self.queue.append(ControlMessages.FLUSH_ON)

    self.terminal_device = os.ttyname(self.pttys[1]) if self.pttys else '/dev/unknown'

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

    self.do_flush_output()

    if self.pttys:
      try:
        os.close(self.pttys[1])
        os.close(self.pttys[0])

        self.input = self.output = None

      except Exception as e:
        e.exc_stack = sys.exc_info()

        warn('Exception raised while closing PTY')
        exception(e)

      self.input = self.output = None

    if self.input:
      _input, self.input = self.input, None
      _input.close()

    if self.output:
      _output, self.output = self.output, None
      _output.close()

  def check_available_input(self):
    if not self.input_fd:
      self.__open_input_stream()

    debug('conio: input stream=%s', self.input)

    if not self.input_fd:
      return False

    try:
      r_read, r_write, r_exc = select.select([self.input_fd], [], [], 0)

      return self.input_fd in r_read

    except Exception, e:
      e.exc_stack = sys.exc_info()
      error('conio.check_available_input: exception happened: e=%s', type(e))
      exception(e, logger = error)
      return False

  def read_raw_input(self, conio_irq):
    while True:
      if not self.check_available_input():
        debug('conio.read_input: no input available')
        return False

      debug('conio.read_input: reading available data from input')

      try:
        if not self.input:
          return False

        s = self.input.read()

        if isinstance(s, types.StringType) and len(s) == 0:
          # EOF
          self.__open_input_stream()
          continue

        for c in s:
          self.queue.append(c)

        self.machine.trigger_irq(conio_irq)

      except IOError, e:
        e.exc_stack = sys.exc_info()
        error('conio.read_raw_input: failed to read from input: input=%s', repr(self.input))
        exception(e, logger = error)
        return False

      return True

  def __escape_char(self, c):
    return chr(c).replace(chr(10), '\\n').replace(chr(13), '\\r')

  def __read_char(self):
    while True:
      try:
        c = self.queue.pop(0)

      except IndexError:
        debug('conio.__read_char: select claims no input available')
        return None

      if type(c) == ControlMessages:
        if c == ControlMessages.CRLF_ON:
          debug('conio: CRLF on')
          self.crlf = True

        elif c == ControlMessages.CRLF_OFF:
          debug('conio: CRLF off')
          self.crlf = False

        elif c == ControlMessages.ECHO_ON:
          debug('conio: echo on')
          self.echo = True

        elif c == ControlMessages.ECHO_OFF:
          debug('conio: echo off')
          self.echo = False

        elif c == ControlMessages.HALT:
          debug('conio: planned halt, execute')
          self.machine.halt()

          return None

        continue

      break

    c = ord(c)

    debug('conio.__read_char: c=%s (%s)', c, self.__escape_char(c))

    return c

  def __write_char(self, c, vm_output = True):
    debug('conio.__write_char: c=%s (%s)', c, self.__escape_char(c))

    try:
      s = chr(c)
      if self.highlight and vm_output:
        s = WHITE(s)

      self.output.write(s)
      self.flush_output()

      if self.stdout_echo:
        sys.stdout.write(s)
        sys.stdout.flush()

    except IOError, e:
      e.exc_stack = sys.exc_info()
      error('Exception raised during console write')
      exception(e, logger = error)

  def read_u8_256(self):
    debug('conio.read_u8_256')

    c = self.__read_char()
    if not c:
      debug('conio.read_u8_256: empty input, signal it downstream')
      return 0xFF

    debug('conio.read_u8_256: input byte is %s', c)

    if self.echo:
      self.__write_char(c, vm_output = False)

    if self.crlf is True and c == CR:
      self.__write_char(LF, vm_output = False)

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
      self.__write_char(ord(c))

    self.__write_char(CR)
    self.__write_char(LF)

class ConioOperationList(enum.IntEnum):
  ECHO = 0

class ConioInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('ConioInterrupt: triggered')

    op = core.REG(Registers.R00).value
    core.REG(Registers.R00).value = 0

    if op == ConioOperationList.ECHO:
      core.cpu.machine.conio.echo = False if core.REG(Registers.R01).value == 0 else True

    else:
      core.WARN('Unknown conio operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

VIRTUAL_INTERRUPTS[InterruptList.CONIO.value] = ConioInterrupt
