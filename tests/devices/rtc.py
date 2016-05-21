from six import iteritems

import ducky.config
import ducky.devices.rtc
import ducky.errors

from ducky.util import UINT8_FMT

from .. import common_run_machine, LOGGER, mock

from hypothesis import given
from hypothesis.strategies import integers

def common_case(**kwargs):
  machine_config = ducky.config.MachineConfig()
  section = machine_config.add_device('rtc', 'ducky.devices.rtc.RTC')

  for name, value in iteritems(kwargs):
    machine_config.set(section, name, value)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False])

  return M.get_device_by_name(section, klass = 'rtc')

def test_sanity():
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST:')

  common_case()

@given(freq = integers(min_value = 0, max_value = 255))
def test_frequency(freq):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: freq=%s', freq)

  rtc = common_case(frequency = freq)
  rtc.boot()

  actual = rtc._mmio_page.read_u8(ducky.devices.rtc.RTCPorts.FREQUENCY)
  expected = freq if freq else ducky.devices.rtc.DEFAULT_FREQ
  assert actual == expected, 'Frequency mismatch: %s expected, %s found' % (expected, actual)

@given(freq = integers(min_value = 256))
def test_high_frequency_init(freq):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: freq=%s', freq)

  try:
    common_case(frequency = freq)

  except ducky.errors.InvalidResourceError:
    pass

  else:
    assert False, 'InvalidResourceError expected, none raised'

@given(freq = integers(min_value = 256))
def test_high_frequency_set(freq):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: freq=%s', freq)

  rtc = common_case()

  try:
    rtc.frequency = freq

  except ducky.errors.InvalidResourceError:
    pass

  else:
    assert False, 'InvalidResourceError expected, none raised'

@given(port = integers(min_value = 0x00, max_value = 0xFF))
def test_read_unknown_port(port):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: port=%s', UINT8_FMT(port))

  rtc = common_case()
  rtc.boot()

  rtc._mmio_page.WARN = mock.MagicMock()

  v = rtc._mmio_page.read_u8(port)

  if port in ducky.devices.rtc.RTCPorts.__members__.values():
    rtc._mmio_page.WARN.assert_not_called()

  else:
    assert v == 0x00
    rtc._mmio_page.WARN.assert_called_with('%s.read_u8: attempt to read unhandled MMIO offset: offset=%s', rtc._mmio_page.__class__.__name__, UINT8_FMT(port))

@given(port = integers(min_value = 0x00, max_value = 0xFF))
def test_write_unknown_port(port):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: port=%s', UINT8_FMT(port))

  rtc = common_case()
  rtc.boot()

  rtc._mmio_page.WARN = mock.MagicMock()

  rtc._mmio_page.write_u8(port, 0)

  if port == ducky.devices.rtc.RTCPorts.FREQUENCY:
    rtc._mmio_page.WARN.assert_not_called()

  else:
    rtc._mmio_page.WARN.assert_called_with('%s.write_u8: attempt to write unhandled MMIO offset: offset=%s, value=%s', rtc._mmio_page.__class__.__name__, UINT8_FMT(port), UINT8_FMT(0))

@given(freq = integers(min_value = 0, max_value = 255))
def test_frequency_change(freq):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: freq=%s', freq)

  rtc = common_case()
  rtc.boot()

  tick = float(1) / float(ducky.devices.rtc.DEFAULT_FREQ)
  assert rtc.frequency == ducky.devices.rtc.DEFAULT_FREQ, 'Frequency mismatch: %s expected, %s found' % (freq, rtc.frequency)
  assert rtc.timer_task.tick == tick, 'Tick mismatch: %s expected, %s found' % (tick, rtc.timer_task.tick)

  rtc._mmio_page.write_u8(ducky.devices.rtc.RTCPorts.FREQUENCY, freq)

  tick = float(1) / float(freq if freq else ducky.devices.rtc.DEFAULT_FREQ)
  assert rtc.frequency == (freq if freq else ducky.devices.rtc.DEFAULT_FREQ), 'Frequency mismatch: %s expected, %s found' % (freq, rtc.frequency)
  assert rtc.timer_task.tick == tick, 'Tick mismatch: %s expected, %s found' % (tick, rtc.timer_task.tick)
