import time
import datetime

from . import Device, IRQProvider, IOProvider, IRQList
from ..errors import InvalidResourceError
from ..mm import UInt8, UINT16_FMT
from ..reactor import RunInIntervalTask

DEFAULT_FREQ = 100.0
DEFAULT_PORT_RANGE = 0x300
PORT_RANGE = 0x0006

class RTCTask(RunInIntervalTask):
  def __init__(self, machine, rtc):
    super(RTCTask, self).__init__(100, self.on_tick)

    self.machine = machine
    self.rtc = rtc

    self.stamp = 0
    self.tick = 1.0 / rtc.frequency

  def on_tick(self, task):
    stamp = time.time()
    diff = stamp - self.stamp
    if diff < self.tick:
      return

    self.stamp = stamp

    self.machine.trigger_irq(self.rtc)

class RTC(IRQProvider, IOProvider, Device):
  def __init__(self, machine, name, frequency = None, port = None, irq = None, *args, **kwargs):
    super(RTC, self).__init__(machine, 'rtc', name, *args, **kwargs)

    self.frequency = frequency or DEFAULT_FREQ
    self.port = port or DEFAULT_PORT_RANGE
    self.ports = range(port, port + 0x0006)
    self.irq = irq or IRQList.TIMER
    self.timer_task = RTCTask(machine, self)

  @classmethod
  def create_from_config(cls, machine, config, section):
    return RTC(machine,
               section,
               frequency = config.getint(section, 'frequency', DEFAULT_FREQ),
               port = config.getint(section, 'port', DEFAULT_PORT_RANGE),
               irq = config.getint(section, 'irq', IRQList.TIMER))

  def boot(self):
    self.machine.DEBUG('RTC.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.machine.reactor.add_task(self.timer_task)

    now = datetime.datetime.now()

    self.machine.INFO('RTC: time %02i:%02i:%02i, date: %02i/%02i/%02i', now.hour, now.minute, now.second, now.day, now.month, now.year - 2000)

  def halt(self):
    for port in self.ports:
      self.machine.unregister_port(port)

    self.machine.reactor.remove_task(self.timer_task)

  def read_u8(self, port):
    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: %s', UINT16_FMT(port))

    port -= self.port
    now = datetime.datetime.now()

    if port == 0x0000:
      return UInt8(now.second).value

    if port == 0x0001:
      return UInt8(now.minute).value

    if port == 0x0002:
      return UInt8(now.hour).value

    if port == 0x0003:
      return UInt8(now.day).value

    if port == 0x0004:
      return UInt8(now.month).value

    if port == 0x0005:
      return UInt8(now.year - 2000).value

    raise InvalidResourceError('Unhandled port: %s', port + self.port)
