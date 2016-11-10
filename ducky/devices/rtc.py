import enum
import time
import datetime

from . import Device, MMIOMemoryPage
from ..errors import InvalidResourceError
from ..mm import u8_t, UINT8_FMT, addr_to_page, u32_t, UINT32_FMT
from ..reactor import RunInIntervalTask
from ..hdt import HDTEntry_Device

DEFAULT_IRQ  = 0x00
DEFAULT_FREQ = 100
DEFAULT_MMIO_ADDRESS = 0x8300

class RTCPorts(enum.IntEnum):
  FREQUENCY = 0x00
  SECOND    = 0x01
  MINUTE    = 0x02
  HOUR      = 0x04
  DAY       = 0x05
  MONTH     = 0x06
  YEAR      = 0x06

class HDTEntry_RTC(HDTEntry_Device):
  _fields_ = HDTEntry_Device.ENTRY_HEADER + [
    ('mmio_address', u32_t)
  ]

  def __init__(self, logger, config, section):
    super(HDTEntry_RTC, self).__init__(logger, section, 'Virtual RTC chip')

    self.mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS)

    logger.debug('%s: mmio-address=%s', self.__class__.__name__, UINT32_FMT(self.mmio_address))

class RTCMMIOMemoryPage(MMIOMemoryPage):
  def read_u8(self, offset):
    self.DEBUG('%s.read_u8: offset=%s', self.__class__.__name__, UINT8_FMT(offset))

    if offset == RTCPorts.FREQUENCY:
      return self._device.frequency

    now = datetime.datetime.now()

    if offset == RTCPorts.SECOND:
      return u8_t(now.second).value

    if offset == RTCPorts.MINUTE:
      return u8_t(now.minute).value

    if offset == RTCPorts.HOUR:
      return u8_t(now.hour).value

    if offset == RTCPorts.DAY:
      return u8_t(now.day).value

    if offset == RTCPorts.MONTH:
      return u8_t(now.month).value

    if offset == RTCPorts.YEAR:
      return u8_t(now.year - 2000).value

    self.WARN('%s.read_u8: attempt to read unhandled MMIO offset: offset=%s', self.__class__.__name__, UINT8_FMT(offset))
    return 0x00

  def write_u8(self, offset, value):
    self.DEBUG('%s.write_u8: offset=%s, value=%s', self.__class__.__name__, UINT8_FMT(offset), UINT8_FMT(value))

    if offset == RTCPorts.FREQUENCY:
      self._device.frequency = value
      self._device.timer_task.update_tick()
      return

    self.WARN('%s.write_u8: attempt to write unhandled MMIO offset: offset=%s, value=%s', self.__class__.__name__, UINT8_FMT(offset), UINT8_FMT(value))

class RTCTask(RunInIntervalTask):
  def __init__(self, machine, rtc):
    super(RTCTask, self).__init__(50, self.on_tick)

    self.machine = machine
    self.rtc = rtc

    self.stamp = 0
    self.tick = 0

    self.update_tick()

  def update_tick(self):
    self.tick = 1.0 / float(self.rtc.frequency)
    self.machine.DEBUG('rtc: new frequency: %i => %f' % (self.rtc.frequency, self.tick))

  def on_tick(self, task):
    stamp = time.time()
    diff = stamp - self.stamp
    self.machine.DEBUG('rtc: tick: stamp=%s, last=%s, diff=%s, tick=%s, ?=%s' % (stamp, self.stamp, diff, self.tick, diff < self.tick))
    if diff < self.tick:
      return

    self.machine.DEBUG('rtc: trigger irq')

    self.stamp = stamp

    self.machine.trigger_irq(self.rtc)

class RTC(Device):
  def __init__(self, machine, name, frequency = None, mmio_address = None, irq = None, *args, **kwargs):
    super(RTC, self).__init__(machine, 'rtc', name, *args, **kwargs)

    self._frequency = None
    self.frequency = frequency or DEFAULT_FREQ

    self.irq = irq or DEFAULT_IRQ
    self.timer_task = RTCTask(machine, self)

    self._mmio_address = mmio_address
    self._mmio_page = None

  @property
  def frequency(self):
    return self._frequency

  @frequency.setter
  def frequency(self, value):
    if value > 0xFF:
      raise InvalidResourceError('Maximum RTC ticks per second is 255')

    if value <= 0:
      value = DEFAULT_FREQ

    self._frequency = value

  @staticmethod
  def create_from_config(machine, config, section):
    return RTC(machine,
               section,
               frequency = config.getint(section, 'frequency', DEFAULT_FREQ),
               mmio_address = config.getint(section, 'mmio-address', DEFAULT_MMIO_ADDRESS),
               irq = config.getint(section, 'irq', DEFAULT_IRQ))

  @staticmethod
  def create_hdt_entries(logger, config, section):
    return [HDTEntry_RTC(logger, config, section)]

  def boot(self):
    self.machine.DEBUG('RTC.boot')

    self._mmio_page = RTCMMIOMemoryPage(self, self.machine.memory, addr_to_page(self._mmio_address))
    self.machine.memory.register_page(self._mmio_page)

    self.machine.reactor.add_task(self.timer_task)
    self.machine.reactor.task_runnable(self.timer_task)

    now = datetime.datetime.now()

    self.machine.tenh('RTC: time %02i:%02i:%02i, date: %02i/%02i/%02i', now.hour, now.minute, now.second, now.day, now.month, now.year - 2000)

  def halt(self):
    self.machine.memory.unregister_page(self._mmio_page)
    self.machine.reactor.remove_task(self.timer_task)
