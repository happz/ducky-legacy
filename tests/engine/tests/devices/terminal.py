from .. import TestCase, mock
from six import iteritems

import ducky.config
import ducky.devices.terminal
import ducky.errors
import ducky.log
import ducky.machine

class TestsStandalonePTYTerminal(TestCase):
  def common_case(self, **kwargs):
    machine = ducky.machine.Machine()

    machine_config = ducky.config.MachineConfig()
    input_section = machine_config.add_device('input', 'ducky.devices.keyboard.KeyboardController')
    output_section = machine_config.add_device('output', 'ducky.devices.tty.TTY')
    terminal_section = machine_config.add_device('terminal', 'ducky.devices.terminal.StandalonePTYTerminal', input = input_section, output = output_section)
    machine_config.set(input_section, 'master', terminal_section)
    machine_config.set(output_section, 'master', terminal_section)

    for name, value in iteritems(kwargs):
      machine_config.set(terminal_section, name, value)

    machine.config = machine_config
    machine.setup_devices()

    return ducky.devices.terminal.StandalonePTYTerminal.create_from_config(machine, machine_config, terminal_section)

  def test_sanity(self):
    t = self.common_case()

    t.input = mock.create_autospec(t.input)
    t.output = mock.create_autospec(t.output)

    t.boot()
    assert t.input.boot.called
    assert t.output.boot.called
    assert t.pttys is not None
    assert t.terminal_device is not None

    t.halt()
    assert t.input.halt.called
    assert t.output.halt.called
    assert t.pttys is None
    assert t.terminal_device is None
