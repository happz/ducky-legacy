from .. import TestCase, mock
from six import iteritems

import ducky.config
import ducky.devices.keyboard
import ducky.errors
import ducky.machine
import ducky.streams

from tests import get_tempfile

class Tests(TestCase):
  def common_case(self, **kwargs):
    machine = ducky.machine.Machine()
    machine.reactor.add_fd = mock.MagicMock()

    machine_config = ducky.config.MachineConfig()
    section = machine_config.add_device('rtc', 'ducky.devices.keyboard.KeyboardController')

    for name, value in iteritems(kwargs):
      machine_config.set(section, name, value)

    return ducky.devices.keyboard.KeyboardController.create_from_config(machine, machine_config, section)

  def test_default(self):
    f = get_tempfile()
    f.close()

    kbd = self.common_case()
    kbd.enqueue_input(ducky.streams.InputStream.create(kbd.machine.LOGGER, f.name))
    kbd.open_input()

    assert kbd.machine.reactor.add_fd.called_with(kbd.input.fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_read_unknown_port(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      self.common_case().read_u8(ducky.devices.keyboard.DEFAULT_PORT_RANGE - 1)
