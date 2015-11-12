from six import iteritems

import ducky.config
import ducky.devices.rtc
import ducky.errors

from .. import TestCase, common_run_machine

def common_case(**kwargs):
  machine_config = ducky.config.MachineConfig()
  section = machine_config.add_device('rtc', 'ducky.devices.rtc.RTC')

  for name, value in iteritems(kwargs):
    machine_config.set(section, name, value)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False])

  return M.get_device_by_name(section, klass = 'rtc')

class Tests(TestCase):
  def test_default(self):
    common_case()

  def test_frequency(self):
    rtc = common_case(frequency = 255)
    assert rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == 255

  def test_high_frequency(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case(frequency = 256)

    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case(frequency = 257)

  def test_unknown_port(self):
    # read from port that's out of range
    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case().read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE - 1)

    # write - this one is out of range...
    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case().write_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE - 1, 100)

    # ... and this one is in range, but only 0x0000 is writable
    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case().write_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE + 1, 100)

  def test_frequency_change(self):
    rtc = common_case()
    assert rtc.frequency == ducky.devices.rtc.DEFAULT_FREQ
    assert rtc.timer_task.tick == 0.01
    assert rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == ducky.devices.rtc.DEFAULT_FREQ

    rtc.write_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE, 200)
    assert rtc.frequency == 200
    assert rtc.timer_task.tick == 0.005
    assert rtc.read_u8(ducky.devices.rtc.DEFAULT_PORT_RANGE) == 200
