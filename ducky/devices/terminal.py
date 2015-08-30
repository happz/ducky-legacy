import os
import sys

from . import Device

class Terminal(Device):
  def __init__(self, machine, name, *args, **kwargs):
    super(Terminal, self).__init__(machine, 'terminal', name, *args, **kwargs)

    self.input = None
    self.output = None

class StreamIOTerminal(Terminal):
  def __init__(self, machine, name, input = None, output = None, streams_in = None, stream_out = None, *args, **kwargs):
    super(StreamIOTerminal, self).__init__(machine, name, *args, **kwargs)

    self.input = input
    self.output = output

    self.input.set_master(self)
    self.output.set_master(self)

    streams_in = streams_in or []

    def get_stream(stream, flags):
      if stream is None:
        return None

      if isinstance(stream, str):
        return open(stream, flags)

      if isinstance(stream, file) or isinstance(stream, orig_file):  # noqa
        return stream

      self.machine.WARN('Unhandled stream type: stream=%s, type=%s', stream, type(stream))
      return None

    self.machine.DEBUG('streams_in=%s', streams_in)
    for stream in streams_in:
      self.input.enqueue_input(get_stream(stream, 'rb'))

    self.output.set_output(get_stream(stream_out, 'wb'))

  @classmethod
  def get_slave_devices(cls, machine, config, section):
    input_name = config.get(section, 'input', None)
    input_device = machine.get_device_by_name(input_name)

    if not input_name or not input_device:
      machine.ERROR('Unknown slave device %s', input_name)

    output_name = config.get(section, 'output', None)
    output_device = machine.get_device_by_name(output_name)

    if not output_name or not output_device:
      machine.ERROR('Unknown slave device %s', output_name)

    return (input_device, output_device)

  @classmethod
  def create_from_config(cls, machine, config, section):
    input_device, output_device = cls.get_slave_devices(machine, config, section)

    return StreamIOTerminal(machine, section, input = input_device, output = output_device, streams_in = [e.strip() for e in config.get(section, 'streams_in', '').split(',')], stream_out = config.get(section, 'stream_out', None))

  def boot(self):
    self.machine.DEBUG('StreamIOTerminal.boot')

    super(StreamIOTerminal, self).boot()

    self.input.boot()
    self.output.boot()

    self.machine.INFO('hid: basic terminal (%s, %s)', self.input.name, self.output.name)

  def halt(self):
    self.machine.DEBUG('StreamIOTerminal.halt')

    super(StreamIOTerminal, self).halt()

    self.input.halt()
    self.output.halt()

    self.machine.DEBUG('Standard terminal halted.')


class StandardIOTerminal(StreamIOTerminal):
  @classmethod
  def create_from_config(cls, machine, config, section):
    input_device, output_device = cls.get_slave_devices(machine, config, section)

    return StandardIOTerminal(machine, section, input = input_device, output = output_device, streams_in = [sys.stdin], stream_out = sys.stdout)


class StandalonePTYTerminal(StreamIOTerminal):
  def __init__(self, *args, **kwargs):
    super(StandalonePTYTerminal, self).__init__(*args, **kwargs)

    self.pttys = None

  @classmethod
  def create_from_config(cls, machine, config, section):
    input_device, output_device = cls.get_slave_devices(machine, config, section)

    return StandalonePTYTerminal(machine, section, input = input_device, output = output_device)

  def boot(self):
    self.machine.DEBUG('StandalonePTYTerminal.boot')

    Terminal.boot(self)

    if self.pttys is not None:
      return

    import pty

    pttys = pty.openpty()

    self.machine.DEBUG('  set I/O stream: pttys=%s', pttys)

    self.input.enqueue_input(pttys[0])
    self.output.set_output(pttys[0])

    self.terminal_device = os.ttyname(pttys[1]) if pttys else '/dev/unknown'

    self.input.boot()
    self.output.boot()

    self.pttys = pttys

    self.machine.INFO('hid: pty terminal (%s, %s), dev %s', self.input.name, self.output.name, self.terminal_device)

  def halt(self):
    self.machine.DEBUG('StandalonePTYTerminal.halt')

    Terminal.halt(self)

    if self.pttys is None:
      return

    self.input.halt()
    self.output.halt()

    try:
      os.close(self.pttys[1])
      os.close(self.pttys[0])

      self.pttys = None

    except Exception:
      self.machine.EXCEPTION('Exception raised while closing PTY')

    self.machine.DEBUG('StandalonePTYTerminal: halted')
