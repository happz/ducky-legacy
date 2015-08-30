import enum

from ..interfaces import IMachineWorker
from ..mm import UINT16_FMT

VIRTUAL_INTERRUPTS = {}

class IRQList(enum.IntEnum):
  """
  List of known IRQ sources.
  """

  TIMER = 0
  CONIO = 1

  IRQ_COUNT = 64


class InterruptList(enum.IntEnum):
  """
  List of known software interrupts.
  """

  HALT    = 0
  BLOCKIO = 1
  VMDEBUG = 2
  CONIO   = 3
  MM      = 4
  MATH    = 5

  INT_COUNT = 64


class IOPorts(enum.IntEnum):
  PORT_COUNT = 65536


class Device(IMachineWorker):
  def __init__(self, machine, klass, name, *args, **kwargs):
    super(Device, self).__init__()

    self.machine = machine
    self.klass = klass
    self.name = name

    self.master = None

  @classmethod
  def create_from_config(cls, machine, config, section):
    return None

  def is_slave(self):
    return self.master is not None

  def get_master(self):
    return self.master

  def set_master(self, master):
    self.master = master


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
