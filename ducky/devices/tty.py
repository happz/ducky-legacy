"""
Very simple character device that just "prints" characters on the screen.
It does not care about dimensions of the display, it kknow only how to
"print" characters. Suited for the most basic output possible - just "print"
chars by writing to this device, and you'll get this written into a stream
attached to the frontend (``stdout``, file, ...).
"""

from . import IOProvider, DeviceFrontend, DeviceBackend
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT, UINT8_FMT
from ..interfaces import IReactorTask

DEFAULT_PORT_RANGE = 0x200

class FrontendFlushTask(IReactorTask):
  def __init__(self, frontend, queue, stream):
    super(FrontendFlushTask, self).__init__()

    self._machine = frontend.machine
    self._queue = queue
    self._stream = stream

  def run(self):
    self._machine.DEBUG('%s.run', self.__class__.__name__)

    b = self._queue.read_out()
    if b is None:
      self._machine.DEBUG('%s.run: no events', self.__class__.__name__)
      return

    self._machine.DEBUG('%s.run: event=%r', self.__class__.__name__, b)
    self._stream.write([b])

class Frontend(DeviceFrontend):
  def __init__(self, machine, name):
    super(Frontend, self).__init__(machine, self.__class__, name)

    self._comm_queue = machine.comm_channel.get_queue(name)
    self._stream = None

    self._flush_task = None
    self._backend = machine.get_device_by_name(name)

  @staticmethod
  def create_from_config(machine, config, section):
    slave = config.get(section, 'slave', default = section)

    return Frontend(machine, slave)

  def boot(self):
    super(Frontend, self).boot()

    self._flush_task = FrontendFlushTask(self, self._comm_queue, self._stream)
    self.machine.reactor.add_task(self._flush_task)
    self.machine.reactor.task_runnable(self._flush_task)

    self._backend.boot()

  def halt(self):
    self._backend.halt()

    self.machine.reactor.remove_task(self._flush_task)

    super(Frontend, self).halt()

  def set_output(self, stream):
    self.machine.DEBUG('%s.set_output: stream=%s', self.__class__.__name__, stream)

    self._stream = stream

  def handle_event(self, event):
    self.machine.DEBUG('%s.handle_event: event=%r', self.__class__.__name__, event)

    self._stream.write([event.b])

class Backend(IOProvider, DeviceBackend):
  def __init__(self, machine, name, stream = None, port = None, *args, **kwargs):
    super(Backend, self).__init__(machine, 'output', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = [port]

    self.comm_queue = machine.comm_channel.create_queue(name)

  @staticmethod
  def create_from_config(machine, config, section):
    return Backend(machine, section,
                   port = config.getint(section, 'port', DEFAULT_PORT_RANGE))

  def __repr__(self):
    return 'basic tty on [%s] as %s' % (', '.join([UINT16_FMT(port) for port in self.ports]), self.name)

  def write_u8(self, port, value):
    self.machine.DEBUG('%s.write_u8: port=%s, value=%s', self.__class__.__name__, UINT16_FMT(port), UINT8_FMT(value))

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s' % UINT16_FMT(port))

    self.comm_queue.write_out(value)

  def boot(self):
    self.machine.DEBUG('%s.boot', self.__class__.__name__)

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.INFO('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('%s.halt', self.__class__.__name__)

    for port in self.ports:
      self.machine.unregister_port(port)
