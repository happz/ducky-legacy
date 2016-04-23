"""
*Terminal* is a device that groups together character two input and output
devices, thus forming a simple channel for bidirectional communication
between VM and user.

Terminal has two slave frontends:
  - *input*, usually a keyboard
  - *output*, from simple TTY to more powerful devices

Terminal then manages input and input streams, passing them to its slave
devices, which then transports events between streams and VM's comm channel.
"""

import os

from . import DeviceFrontend, get_driver_creator
from ..streams import InputStream, OutputStream

def parse_io_streams(machine, config, section):
  streams_in, stream_out = None, None

  if config.has_option(section, 'streams_in'):
    streams_in = [InputStream.create(machine, e.strip()) for e in config.get(section, 'streams_in').split(',')]

  if config.has_option(section, 'stream_out'):
    stream_out = OutputStream.create(machine, config.get(section, 'stream_out'))

  return (streams_in, stream_out)

def get_slave_devices(machine, config, section):
  machine.DEBUG('get_slave_devices: section=%s', section)

  input_device, output_device = None, None

  input_spec = config.get(section, 'input', None)
  output_spec = config.get(section, 'output', None)

  if input_spec is not None:
    backend_name, frontend_driver = input_spec.split(':')

    input_device = get_driver_creator(frontend_driver)(machine, machine.config, backend_name)

  if output_spec is not None:
    backend_name, frontend_driver = output_spec.split(':')

    output_device = get_driver_creator(frontend_driver)(machine, machine.config, backend_name)

  return (input_device, output_device)

class Terminal(DeviceFrontend):
  def __init__(self, machine, name, echo = False, *args, **kwargs):
    super(Terminal, self).__init__(machine, 'terminal', name)

    self._input = None
    self._output = None

    self._echo = echo
    self._input_read_u8_orig = None

  def _input_read_u8_echo(self, *args, **kwargs):
    c = self._input_read_u8_orig(*args, **kwargs)

    if c != 0xFF:
      self._output.write_u8(self._output.port, c)

    return c

  def _patch_echo(self, restore = False):
    D = self.machine.DEBUG

    D('%s._patch_echo: echo=%s, restore=%s', self.__class__.__name__, self._echo, restore)

    if restore is True and self._input_read_u8_orig is not None:
      self._input.read_u8, self._input_read_u8_orig = self._input_read_u8_orig, None

    elif self._echo is True:
      assert self._input is not None
      assert hasattr(self._input, 'read_u8')
      assert hasattr(self._output, 'write_u8')

      self._input_read_u8_orig, self._input.read_u8 = self._input.read_u8, self._input_read_u8_echo

    D('%s.patch_echo: input.read_u8=%s, orig_input.read_u8=%s', self.__class__.__name__, self._input.read_u8, self._input_read_u8_orig)

  def boot(self):
    super(Terminal, self).boot()

    # self._patch_echo()

  def halt(self):
    super(Terminal, self).halt()

    # self._patch_echo(restore = True)

class StreamIOTerminal(Terminal):
  def __init__(self, machine, name, input_device = None, output_device = None, *args, **kwargs):
    super(StreamIOTerminal, self).__init__(machine, name, *args, **kwargs)

    machine.DEBUG('%s: name=%s, input_device=%s, output_device=%s', self.__class__.__name__, name, input_device, output_device)

    self._input = input_device
    self._output = output_device

    self._streams_in = []
    self._stream_out = None

    self._input.master = self
    self._output.master = self

  def enqueue_input_stream(self, stream):
    self.machine.DEBUG('%s.enqueue_input_stream: stream=%r', self.__class__.__name__, stream)

    self._input.enqueue_stream(stream)

  def enqueue_streams(self, streams_in = None, stream_out = None):
    self.machine.DEBUG('%s.enqueue_streams: streams_in=%s, stream_out=%s', self.__class__.__name__, streams_in, stream_out)

    if streams_in is not None:
      streams_in = streams_in or []

      for stream in streams_in:
        self.enqueue_input_stream(stream)

      self._streams_in = streams_in

    if stream_out is not None:
      self._stream_out = stream_out
      self._output.set_output(stream_out)

  @staticmethod
  def create_from_config(machine, config, section):
    input_device, output_device = get_slave_devices(machine, config, section)

    term = StreamIOTerminal(machine, section, input_device = input_device, output_device = output_device, echo = config.getbool(section, 'echo', False))

    streams_in, stream_out = parse_io_streams(machine, config, section)
    term.enqueue_streams(streams_in = streams_in, stream_out = stream_out)

    return term

  def boot(self):
    super(StreamIOTerminal, self).boot()

    self._input.boot()
    self._output.boot()

    self.machine.tenh('hid: basic terminal (%s, %s)', self._input.name, self._output.name)

  def halt(self):
    super(StreamIOTerminal, self).halt()

    self._input.halt()
    self._output.halt()

    for stream in self._streams_in:
      stream.close()

    if self._stream_out is not None:
      self._stream_out.flush()
      self._stream_out.close()

    self.machine.DEBUG('Standard terminal halted.')

class StandardIOTerminal(StreamIOTerminal):
  @staticmethod
  def create_from_config(machine, config, section):
    input_device, output_device = get_slave_devices(machine, config, section)

    term = StandardIOTerminal(machine, section, input_device = input_device, output_device = output_device)
    term.enqueue_streams(streams_in = [InputStream.create(machine, '<stdin>')], stream_out = OutputStream.create(machine, '<stdout>'))

    return term

class StandalonePTYTerminal(StreamIOTerminal):
  def __init__(self, *args, **kwargs):
    super(StandalonePTYTerminal, self).__init__(*args, **kwargs)

    self.pttys = None

  @staticmethod
  def create_from_config(machine, config, section):
    input_device, output_device = get_slave_devices(machine, config, section)

    term = StandalonePTYTerminal(machine, section, input_device = input_device, output_device = output_device, echo = config.getbool(section, 'echo', False))

    streams_in, stream_out = parse_io_streams(machine, config, section)
    term.enqueue_streams(streams_in = streams_in, stream_out = stream_out)

    return term

  def boot(self):
    self.machine.DEBUG('StandalonePTYTerminal.boot')

    Terminal.boot(self)

    if self.pttys is not None:
      return

    import pty

    pttys = pty.openpty()

    self.machine.DEBUG('  set I/O stream: pttys=%s', pttys)

    self.enqueue_streams(streams_in = [InputStream.create(self.machine, pttys[0])], stream_out = OutputStream.create(self.machine, pttys[0]))

    self.terminal_device = os.ttyname(pttys[1]) if pttys else '/dev/unknown'

    self._input.boot()
    self._output.boot()

    self.pttys = pttys

    self.machine.tenh('hid: pty terminal (%s, %s), dev %s', self._input.name, self._output.name, self.terminal_device)

  def halt(self):
    self.machine.DEBUG('StandalonePTYTerminal.halt')

    Terminal.halt(self)

    if self.pttys is None:
      return

    self._input.halt()
    self._output.halt()

    try:
      os.close(self.pttys[1])
      os.close(self.pttys[0])

      self.pttys = None
      self.terminal_device = None

    except Exception:
      self.machine.EXCEPTION('Exception raised while closing PTY')

    self.machine.DEBUG('StandalonePTYTerminal: halted')
