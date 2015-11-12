from six import iteritems

import ducky.config
import ducky.devices.keyboard
import ducky.errors
import ducky.machine
import ducky.streams

from .. import TestCase, get_tempfile, common_run_machine, mock

def common_case(**kwargs):
  machine_config = ducky.config.MachineConfig()
  section = machine_config.add_device('input', 'ducky.devices.keyboard.KeyboardController')

  for name, value in iteritems(kwargs):
    machine_config.set(section, name, value)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False])

  return M.get_device_by_name(section, klass = 'input')

class Tests(TestCase):
  def test_default(self):
    f = get_tempfile()
    f.close()

    kbd = common_case()
    kbd.machine.reactor.add_fd = mock.MagicMock()
    kbd.enqueue_input(ducky.streams.InputStream.create(kbd.machine.LOGGER, f.name))
    kbd.machine.boot()

    assert kbd.machine.reactor.add_fd.called_with(kbd.input.fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_read_unknown_port(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      common_case().read_u8(ducky.devices.keyboard.DEFAULT_PORT_RANGE - 1)
