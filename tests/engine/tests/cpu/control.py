from six.moves import range

import ducky.cpu.coprocessor.control
import ducky.errors

from ducky.cpu.coprocessor.control import ControlRegisters
from ducky.util import F

from .. import TestCase, common_run_machine

def create_machine(ivt_address = None, pt_address = None, privileged = True, **kwargs):
  machine_config = ducky.config.MachineConfig()

  if ivt_address is not None or pt_address is not None:
    machine_config.add_section('cpu')

    if ivt_address is not None:
      machine_config.set('cpu', 'ivt-address', ivt_address)

    if pt_address is not None:
      machine_config.set('cpu', 'pt-address', pt_address)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False], **kwargs)

  return M

class Tests(TestCase):
  def test_unprivileged(self):
    M = create_machine()

    core = M.cpus[0].cores[0]

    assert core.privileged is True

    core.control_coprocessor.read(ControlRegisters.CR0)

    core.privileged = False

    with self.assertRaises(ducky.errors.AccessViolationError):
      core.control_coprocessor.read(ControlRegisters.CR0)

  def test_cpuid(self):
    M = create_machine(cpus = 4, cores = 4)

    for i in range(0, 4):
      for j in range(0, 4):
        core = M.cpus[i].cores[j]
        core.privileged = True
        assert core.privileged is True

        cpuid_expected = 0xFFFFFFFF & ((i << 16) | j)
        cpuid_read = core.control_coprocessor.read(ControlRegisters.CR0)
        assert cpuid_expected == cpuid_read, 'CPUID mismatch: cpu=%i, core=%i, rcpu=%i, rcore=%i, expected=%i, read=%i' % (i, j, core.cpu.id, core.id, cpuid_expected, cpuid_read)

    with self.assertRaises(ducky.cpu.coprocessor.control.ReadOnlyRegisterError):
      M.cpus[0].cores[0].control_coprocessor.write(ControlRegisters.CR0, 0xFF)

  def test_ivt(self):
    M = create_machine(ivt_address = 0xC7C7DEAD)

    core = M.cpus[0].cores[0]

    core.privileged = True
    assert core.privileged is True, 'Core is not in privileged mode'

    v = core.control_coprocessor.read(ControlRegisters.CR1)
    assert v == 0xC7C7DEAD, F('IVT expected {expected:L}, {actual:L} found instead', expected = 0xC7C7DEAD, actual = v)

    core.control_coprocessor.write(ControlRegisters.CR1, 0xF5EEF00D)

    v = core.control_coprocessor.read(ControlRegisters.CR1)
    assert v == 0xF5EEF00D, F('IVT expected {expected:L}, {actual:L} found instead', expected = 0xF5EEF00D, actual = v)

  def test_pt(self):
    M = create_machine(pt_address = 0xC7C7DEAD)

    core = M.cpus[0].cores[0]

    core.privileged = True
    assert core.privileged is True, 'Core is not in privileged mode'

    v = core.control_coprocessor.read(ControlRegisters.CR2)
    assert v == 0xC7C7DEAD, F('PT expected {expected:L}, {actual:L} found instead', expected = 0xC7C7DEAD, actual = v)

    core.control_coprocessor.write(ControlRegisters.CR2, 0xF5EEF00D)

    v = core.control_coprocessor.read(ControlRegisters.CR2)
    assert v == 0xF5EEF00D, F('PT expected {expected:L}, {actual:L} found instead', expected = 0xF5EEF00D, actual = v)
