from six import iteritems

import ducky.config
import ducky.devices.terminal
import ducky.errors
import ducky.log
import ducky.machine

from .. import TestCase, mock, common_run_machine

def common_case(**kwargs):
  machine_config = ducky.config.MachineConfig()

  input_section = machine_config.add_device('input', 'ducky.devices.keyboard.Backend')
  output_section = machine_config.add_device('output', 'ducky.devices.tty.Backend')
  terminal_section = machine_config.add_device('terminal', 'ducky.devices.terminal.StandalonePTYTerminal', input = input_section, output = output_section)

  machine_config.set(input_section, 'master', terminal_section)
  machine_config.set(output_section, 'master', terminal_section)

  machine_config.set(terminal_section, 'input',  input_section + ':ducky.devices.keyboard.Frontend')
  machine_config.set(terminal_section, 'output', output_section + ':ducky.devices.tty.Frontend')

  for name, value in iteritems(kwargs):
    machine_config.set(terminal_section, name, value)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False])

  return M.get_device_by_name(terminal_section, klass = 'terminal')

class TestsStandalonePTYTerminal(TestCase):
  def test_sanity(self):
    t = common_case()

    t._input = mock.create_autospec(t._input)
    t._output = mock.create_autospec(t._output)

    t.boot()
    assert t._input.boot.called
    assert t._output.boot.called
    assert t.pttys is not None
    assert t.terminal_device is not None

    t.halt()
    assert t._input.halt.called
    assert t._output.halt.called
    assert t.pttys is None
    assert t.terminal_device is None
