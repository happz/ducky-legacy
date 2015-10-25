import mock
import unittest

import ducky.config
import ducky.devices.keyboard
import ducky.errors
import ducky.machine

from tests import get_tempfile

class Tests(unittest.TestCase):
  def common_case(self, **kwargs):
    machine = ducky.machine.Machine()
    machine.reactor.add_fd = mock.MagicMock()

    machine_config = ducky.config.MachineConfig()
    section = machine_config.add_device('rtc', 'ducky.devices.keyboard.KeyboardController')

    for name, value in kwargs.iteritems():
      machine_config.set(section, name, value)

    return ducky.devices.keyboard.KeyboardController.create_from_config(machine, machine_config, section)

  def test_default(self):
    self.common_case()

  def test_stream_string(self):
    f = get_tempfile()
    f.close()

    kbd = self.common_case()
    kbd.enqueue_input(f.name)
    kbd.open_input()

    assert kbd.input.name == f.name
    assert kbd.input_fd == kbd.input.fileno()
    assert kbd.machine.reactor.add_fd.called_with(kbd.input_fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_stream_file(self):
    f = get_tempfile()

    kbd = self.common_case()
    kbd.enqueue_input(f)
    kbd.open_input()

    assert kbd.input == f
    assert kbd.input_fd == kbd.input.fileno()
    assert kbd.machine.reactor.add_fd.called_with(kbd.input_fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_stream_fd(self):
    f = get_tempfile()

    kbd = self.common_case()
    kbd.enqueue_input(f.fileno())
    kbd.open_input()

    assert kbd.input is None
    assert kbd.input_fd == f.fileno()
    assert kbd.machine.reactor.add_fd.called_with(kbd.input_fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_stream_fileno(self):
    f = get_tempfile()

    class FileWrapper(object):
      def fileno(self):
        return f.fileno()

    fw = FileWrapper()
    kbd = self.common_case()
    kbd.enqueue_input(fw)
    kbd.open_input()

    assert kbd.input is fw
    assert kbd.input_fd == f.fileno()
    assert kbd.machine.reactor.add_fd.called_with(kbd.input_fd, on_read = kbd.handle_raw_input, on_error = kbd.handle_input_error)

  def test_stream_unknown(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      kbd = self.common_case()
      kbd.enqueue_input(object())
      kbd.open_input()
