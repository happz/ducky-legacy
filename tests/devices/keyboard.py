from six import iteritems

import ducky.config
import ducky.devices.keyboard
import ducky.errors
import ducky.machine
import ducky.streams

from .. import TestCase, get_tempfile, common_run_machine, mock

def common_case(**kwargs):
  machine_config = ducky.config.MachineConfig()
  section_backend = machine_config.add_device('input', 'ducky.devices.keyboard.Backend')
  section_frontend = machine_config.add_device('input', 'ducky.devices.keyboard.Frontend')

  for name, value in iteritems(kwargs):
    machine_config.set(section_backend, name, value)

  machine_config.set(section_backend, 'master', section_frontend)
  machine_config.set(section_frontend, 'slave', section_backend)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False])

  return M.get_device_by_name(section_frontend, 'input'), M.get_device_by_name(section_backend, klass = 'input')

class Tests(TestCase):
  def test_default(self):
    f = get_tempfile()
    f.close()

    frontend, backend = common_case()
    M = frontend.machine

    M.reactor.add_fd = mock.MagicMock()
    M.reactor.remove_fd = mock.MagicMock()
    frontend.enqueue_stream(ducky.streams.InputStream.create(M, f.name))
    M.boot()

    try:
      assert M.reactor.add_fd.called_with(frontend._stream.fd, on_read = frontend._handle_raw_input, on_error = frontend._handle_input_error)

    finally:
      M.halt()

  def test_read_unknown_port(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      frontend, backend = common_case()

      backend.read_u8(ducky.devices.keyboard.DEFAULT_PORT_RANGE - 1)
