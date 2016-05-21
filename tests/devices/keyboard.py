from six import iteritems

import ducky.config
import ducky.devices.keyboard
import ducky.errors
import ducky.machine
import ducky.streams

from ducky.util import UINT8_FMT

from .. import get_tempfile, common_run_machine, mock, LOGGER
from hypothesis import given
from hypothesis.strategies import integers

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

def test_default():
  f = get_tempfile()
  f.close()

  frontend, backend = common_case()
  M = frontend.machine

  M.reactor.add_fd = mock.MagicMock()
  M.reactor.remove_fd = mock.MagicMock()
  frontend.enqueue_stream(ducky.streams.InputStream.create(M, f.name))
  M.boot()

  try:
    M.reactor.add_fd.assert_called_with(frontend._stream.fd, on_read = frontend._handle_raw_input, on_error = frontend._handle_input_error)

  finally:
    M.halt()

@given(port = integers(min_value = 0x00, max_value = 0xFF))
def test_read_unknown_port(port):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: port=%s', UINT8_FMT(port))

  frontend, backend = common_case()
  backend.boot()

  backend._mmio_page.WARN = mock.MagicMock()

  v = backend._mmio_page.read_u8(port)

  if port == ducky.devices.keyboard.KeyboardPorts.STATUS:
    assert v == 0x00
    backend._mmio_page.WARN.assert_not_called()

  elif port == ducky.devices.keyboard.KeyboardPorts.DATA:
    assert v == 0xFF
    backend._mmio_page.WARN.assert_not_called()

  else:
    assert v == 0x00
    backend._mmio_page.WARN.assert_called_with('%s.read_u8: attempt to read raw offset: offset=%s', backend._mmio_page.__class__.__name__, UINT8_FMT(port))
