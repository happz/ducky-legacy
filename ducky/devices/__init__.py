"""
Emulating different virtual devices like keyboard, display, disks...
"""

import importlib

from ..interfaces import IMachineWorker
from ..mm import VirtualMemoryPage

class Device(IMachineWorker):
  """
  Base class for all devices. Serves more like an API description.

  :param ducky.machine.Machine machine: VM this device belongs to.
  :param str klass: device family (input, output, snapshot, ...)
  :param str name: device name. Maps directly to a section of config
    file that hosts setup for this device.
  """

  def __init__(self, machine, klass, name):
    super(Device, self).__init__()

    self.machine = machine
    self.klass = klass
    self.name = name

    self.logger = machine.LOGGER
    self.master = None

  @staticmethod
  def create_from_config(machine, config, section):
    """
    Create new instance, configured exactly as requested by configuration file.

    :param ducky.machine.Machine machine: VM this device belongs to.
    :param ducky.config.MachineConfig config: configuration file.
    :param str section: name of config section with this device's setup.
    """

    raise NotImplementedError()

  @staticmethod
  def create_hdt_entries(logger, config, section):
    """
    Create ``HDT`` entries for this device, based on configuration file.

    :param logging.Logger logger: logger to use for logging.
    :param ducky.config.MachineConfig config: configuration file.
    :param str section: name of config section with this device's setup.
    :rtype: ``list`` of :py:class:`ducky.hdt.HDTEntry`
    :returns: list of ``HDT`` entries. This list is then appended to entries
      of other devices.
    """

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
  """
  Frontend is a special component of a device, that interfaces communication
  channels from user and internal queues.
  """

  def set_backend(self, device):
    """
    Set backend counterpart.

    :param ducky.devices.DeviceFrontend device: backend part.
    """

    self.backend = device

class DeviceBackend(Device):
  """
  Backend is a special component of a device, which is connected to internal
  queues, and processes events in the queue, originating from user via its
  frontend counterpart.
  """

  def set_frontend(self, device):
    """
    Set frontend counterpart.

    :param ducky.device.DeviceFrontend device: frontend part.
    """

    self.frontend = device


class MMIOMemoryPage(VirtualMemoryPage):
  """
  Memory page, suited for memory-mapped IO, supported by a device driver.

  :param ducky.devices.Device device: device instance, backing this memory
    page.
  """

  def __init__(self, device, *args, **kwargs):
    super(MMIOMemoryPage, self).__init__(*args, **kwargs)

    self._device = device

def get_driver(driver_class):
  """
  Get Python class, implementing device driver, by its name.

  :param str driver_class: path to a class, e.g. ``ducky.devices.rtc.RTC``.
  :returns: driver class.
  """

  driver = driver_class.split('.')

  driver_module = importlib.import_module('.'.join(driver[0:-1]))
  driver_class = getattr(driver_module, driver[-1])

  return driver_class
