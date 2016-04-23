import enum
import importlib

from ..interfaces import IMachineWorker
from ..mm import UINT16_FMT
from ..errors import InvalidResourceError

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


class IOProvider(object):
  def is_port_protected(self, port, read = True):
    return False

  def read_u8(self, port):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

  def read_u16(self, port):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

  def read_u32(self, port):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

  def write_u8(self, port, value):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

  def write_u16(self, port, value):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))

  def write_u32(self, port, value):
    raise InvalidResourceError('Unhandled port: port={}'.format(UINT16_FMT(port)))


def get_driver_creator(driver_class):
  driver = driver_class.split('.')

  driver_module = importlib.import_module('.'.join(driver[0:-1]))
  driver_class = getattr(driver_module, driver[-1])

  return driver_class.create_from_config
