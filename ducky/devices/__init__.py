import enum

from ..interfaces import IMachineWorker
from ..mm import UINT16_FMT

VIRTUAL_INTERRUPTS = {}

class IRQList(enum.IntEnum):
  """
  List of known IRQ sources.
  """

  # HW devices
  TIMER    = 0
  KEYBOARD = 1

  # SW interrupts and exceptions
  HALT    = 32
  BLOCKIO = 33
  VMDEBUG = 34
  MM      = 35
  MATH    = 36

  IRQ_COUNT = 64


class IOPorts(enum.IntEnum):
  PORT_COUNT = 65536


class Device(IMachineWorker):
  def __init__(self, machine, klass, name, *args, **kwargs):
    super(Device, self).__init__()

    self.machine = machine
    self.klass = klass
    self.name = name

    self.master = None

  @staticmethod
  def create_from_config(machine, config, section):
    return None

  def is_slave(self):
    return self.master is not None

  def get_master(self):
    return self.master


class IRQProvider(object):
  pass


class IOProvider(object):
  def is_port_protected(self, port, read = True):
    return False

  def read_u8(self, port):
    self.machine.WARN('Unhandled port: %s', UINT16_FMT(port))

    return None

  def read_u16(self, port):
    self.machine.WARN('Unhandled port: %s', UINT16_FMT(port))

    return None

  def write_u8(self, port, value):
    self.machine.WARN('Unhandled port: %s', UINT16_FMT(port))

  def write_u16(self, port, value):
    self.machine.WARN('Unhandled port: %s', UINT16_FMT(port))
