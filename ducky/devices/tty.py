"""
Very simple character device that just "prints" characters on the screen.
It does not care about dimensions of the display, it kknow only how to
"print" characters. Suited for the most basic output possible - just "print"
chars by writing to this device, and you'll get this written into a stream
attached to the frontend (``stdout``, file, ...).
"""

import enum
from . import DeviceFrontend, DeviceBackend, MMIOMemoryPage
from ..mm import UINT8_FMT, addr_to_page, UINT32_FMT, u32_t
from ..interfaces import IReactorTask
from ..hdt import HDTEntry_Device

DEFAULT_MMIO_ADDRESS = 0x8200

class TTYPorts(enum.IntEnum):
  DATA = 0x00

class TTYMMIOMemoryPage(MMIOMemoryPage):
  def write_u8(self, offset, value):
    self.DEBUG('%s.write_u8: offset=%s, value=%s', self.__class__.__name__, UINT8_FMT(offset), UINT8_FMT(value))

    if offset == TTYPorts.DATA:
      self._device.comm_queue.write_out(value)
      self._device.frontend.wakeup_flush()
      return

    self.WARN('%s.write_u8: attempt to write to a virtual page: offset=%s', self.__class__.__name__, UINT8_FMT(offset))

class HDTEntry_TTY(HDTEntry_Device):
  _fields_ = HDTEntry_Device.ENTRY_HEADER + [
    ('mmio_address', u32_t)
  ]

  def __init__(self, logger, config, section):
    super(HDTEntry_TTY, self).__init__(logger, section, 'Virtual TTY')

    self.mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS)

    logger.debug('%s: mmio-address=%s', self.__class__.__name__, UINT32_FMT(self.mmio_address))

class FrontendFlushTask(IReactorTask):
  def __init__(self, frontend, queue, stream):
    super(FrontendFlushTask, self).__init__()

    self._frontend = frontend
    self._machine = frontend.machine
    self._queue = queue
    self._stream = stream

  def set_output(self, stream):
    self._stream = stream

  def run(self):
    self._machine.DEBUG('%s.run', self.__class__.__name__)

    b = self._queue.read_out()
    if b is None:
      self._machine.DEBUG('%s.run: no events', self.__class__.__name__)
      self._frontend.sleep_flush()
      return

    self._machine.DEBUG('%s.run: event=%r', self.__class__.__name__, b)
    self._stream.write([b])

class Frontend(DeviceFrontend):
  def __init__(self, machine, name):
    super(Frontend, self).__init__(machine, self.__class__, name)

    self._comm_queue = machine.comm_channel.get_queue(name)
    self._stream = None

    self._flush_task = None
    self.set_backend(machine.get_device_by_name(name))
    self.backend.set_frontend(self)

  @staticmethod
  def create_from_config(machine, config, section):
    slave = config.get(section, 'slave', default = section)

    return Frontend(machine, slave)

  def boot(self):
    super(Frontend, self).boot()

    self._flush_task = FrontendFlushTask(self, self._comm_queue, self._stream)
    self.machine.reactor.add_task(self._flush_task)

    self.backend.boot()

  def halt(self):
    self.backend.halt()

    self.machine.reactor.remove_task(self._flush_task)

    super(Frontend, self).halt()

  def set_output(self, stream):
    self.machine.DEBUG('%s.set_output: stream=%s', self.__class__.__name__, stream)

    self._stream = stream

    if self._flush_task is not None:
      self._flush_task.set_output(stream)

  def flush(self):
    while not self._comm_queue.is_empty_out():
      self._flush_task.run()

  def wakeup_flush(self):
    if self._flush_task is None:
      return

    self.machine.reactor.task_runnable(self._flush_task)

  def sleep_flush(self):
    if self._flush_task is None:
      return

    self.machine.reactor.task_suspended(self._flush_task)

  def close(self, allow = False):
    if allow is True:
      self._stream.allow_close = True

    self._stream.close()

  def tenh_enable(self):
    if self._stream is not None:
      self._stream.allow_close = False

class Backend(DeviceBackend):
  def __init__(self, machine, name, stream = None, mmio_address = None, *args, **kwargs):
    super(Backend, self).__init__(machine, 'output', name, *args, **kwargs)

    self._mmio_address = mmio_address or DEFAULT_MMIO_ADDRESS
    self._mmio_page = None

    self.comm_queue = machine.comm_channel.create_queue(name)

  @staticmethod
  def create_from_config(machine, config, section):
    return Backend(machine, section,
                   mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS))

  @staticmethod
  def create_hdt_entries(logger, config, section):
    return [HDTEntry_TTY(logger, config, section)]

  def __repr__(self):
    return 'basic tty on [%s] as %s' % (UINT32_FMT(self._mmio_address), self.name)

  def tenh(self, s, *args):
    self.machine.DEBUG('%s.tenh: s="%s", args=%s', self.__class__.__name__, s, args)

    s = s % args

    for c in s:
      self.comm_queue.write_out(ord(c))

    self.frontend.wakeup_flush()

  def tenh_enable(self):
    self.frontend.tenh_enable()

  def tenh_flush_stream(self):
    self.frontend.flush()

  def tenh_close_stream(self):
    self.frontend.close(allow = True)

  def boot(self):
    self.machine.DEBUG('%s.boot', self.__class__.__name__)

    self._mmio_page = TTYMMIOMemoryPage(self, self.machine.memory, addr_to_page(self._mmio_address))
    self.machine.memory.register_page(self._mmio_page)

    self.machine.tenh('hid: %s', self)

  def halt(self):
    self.machine.DEBUG('%s.halt', self.__class__.__name__)

    self.machine.memory.unregister_page(self._mmio_page)
