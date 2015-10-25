import unittest

import ducky.config
import ducky.devices.rtc
import ducky.errors

class Tests(unittest.TestCase):
  def common_case(self, **kwargs):
    machine_config = ducky.config.MachineConfig()
    section = machine_config.add_device('rtc', 'ducky.devices.rtc.RTC')

    for name, value in kwargs.iteritems():
      machine_config.set(section, name, value)

    return ducky.devices.rtc.RTC.create_from_config(None, machine_config, section)

  def test_default(self):
    self.common_case()

  def test_frequency(self):
    rtc = self.common_case(frequency = 256)
    rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == 256

  def test_high_frequency(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      self.common_case(frequency = 257)

  def test_unknown_port(self):
    # read from port that's out of range
    with self.assertRaises(ducky.errors.InvalidResourceError):
      self.common_case().read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE - 1)

    # write - this one is out of range...
    with self.assertRaises(ducky.errors.InvalidResourceError):
      self.common_case().read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE - 1)

    # ... and this one is in range, but only 0x0000 is writable
    with self.assertRaises(ducky.errors.InvalidResourceError):
      self.common_case().read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE - 1)

  def test_frequency_change(self):
    rtc = self.common_case()
    assert rtc.frequency == ducky.devices.rtc.DEFAULT_FREQ
    assert rtc.timer_task.tick == 0.01
    assert rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == ducky.devices.rtc.DEFAULT_FREQ

    rtc.write_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE, 200)
    assert rtc.frequency == 200
    assert rtc.timer_task.tick == 0.005
    assert rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == 200
