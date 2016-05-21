import enum
import importlib

from ..interfaces import IMachineWorker
from ..mm import VirtualMemoryPage

VIRTUAL_INTERRUPTS = {}

class IRQList(enum.IntEnum):
  """
  List of known IRQ sources.
  """

  # HW devices
  TIMER    = 0
  KEYBOARD = 1
  BIO      = 2

  # SW interrupts and exceptions
  HALT    = 16
  BLOCKIO = 17
  VMDEBUG = 18

  IRQ_COUNT = 32


class IOPorts(enum.IntEnum):
  PORT_COUNT = 65536


class Device(IMachineWorker):
  def __init__(self, machine, klass, name):
    super(Device, self).__init__()

    self.machine = machine
    self.klass = klass
    self.name = name

    self.logger = machine.LOGGER
    self.master = None

  @staticmethod
  def create_from_config(machine, config, section):
    raise NotImplementedError()

  @staticmethod
  def create_hdt_entries(logger, config, section):
    return []

  def boot(self):
    self.logger.debug('%s.boot', self.__class__.__name__)
    pass

  def halt(self):
    self.logger.debug('%s.halt', self.__class__.__name__)
    pass

  def is_slave(self):
    return self.master is not None

  def get_master(self):
    return self.master


class DeviceFrontend(Device):
  def set_backend(self, device):
    self.backend = device

class DeviceBackend(Device):
  def set_frontend(self, device):
    self.frontend = device

class IRQProvider(object):
  pass


class MMIOMemoryPage(VirtualMemoryPage):
  def __init__(self, device, *args, **kwargs):
    super(MMIOMemoryPage, self).__init__(*args, **kwargs)

    self._device = device

def get_driver(driver_class):
  driver = driver_class.split('.')

  driver_module = importlib.import_module('.'.join(driver[0:-1]))
  driver_class = getattr(driver_module, driver[-1])

  return driver_class
