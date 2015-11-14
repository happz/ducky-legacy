from six.moves import range

import ducky.cpu.coprocessor.control
import ducky.errors

from ducky.cpu.coprocessor.control import ControlRegisters

from .. import TestCase, common_run_machine

def create_machine(ivt_address = None, privileged = True, **kwargs):
  machine_config = ducky.config.MachineConfig()

  if ivt_address is not None:
    machine_config.add_section('cpu')
    machine_config.set('cpu', 'ivt-address', ivt_address)

  M = common_run_machine(machine_config = machine_config, post_setup = [lambda _M: False], **kwargs)

  return M

class Tests(TestCase):
  def test_unprivileged(self):
    M = create_machine()

    core = M.cpus[0].cores[0]

    assert core.privileged == False

    with self.assertRaises(ducky.errors.AccessViolationError):
      core.control_coprocessor.read(ControlRegisters.CR0)

    core.privileged = True

    assert core.privileged == True
    core.control_coprocessor.read(ControlRegisters.CR0)

  def test_cpuid(self):
    M = create_machine(cpus = 4, cores = 4)

    for i in range(0, 4):
      for j in range(0, 4):
        core = M.cpus[i].cores[j]
        core.privileged = True
        assert core.privileged == True

        cpuid_expected = 0xFFFF & ((i << 8) | j)
        cpuid_read = core.control_coprocessor.read(ControlRegisters.CR0)
        assert cpuid_expected == cpuid_read, 'CPUID mismatch: cpu=%i, core=%i, rcpu=%i, rcore=%i, expected=%i, read=%i' % (i, j, core.cpu.id, core.id, cpuid_expected, cpuid_read)

    with self.assertRaises(ducky.cpu.coprocessor.control.ReadOnlyRegisterError):
      M.cpus[0].cores[0].control_coprocessor.write(ControlRegisters.CR0, 0xFF)

  def test_ivt(self):
    M = create_machine(ivt_address = 0x02DEAD)

    core = M.cpus[0].cores[0]

    core.privileged = True
    assert core.privileged == True

    assert core.control_coprocessor.read(ControlRegisters.CR1) == 0xDEAD
    assert core.control_coprocessor.read(ControlRegisters.CR2) == 0x02

    core.control_coprocessor.write(ControlRegisters.CR1, 0xF00D)
    core.control_coprocessor.write(ControlRegisters.CR2, 0xF0)

    assert core.control_coprocessor.read(ControlRegisters.CR1) == 0xF00D
    assert core.control_coprocessor.read(ControlRegisters.CR2) == 0xF0
