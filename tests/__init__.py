import patch

import os
import sys
import tempfile

import config
import cpu.assemble
import cpu.registers
import console
import core
import machine
import mm
import util

def prepare_file(size, messages = None, pattern = 0xDE):
  f_tmp = tempfile.NamedTemporaryFile('w+b', delete = False)

  # fill file with pattern
  f_tmp.seek(0)
  for _ in range(0, size):
    f_tmp.write(chr(pattern))

  messages = messages or []

  # write out messages
  for offset, msg in messages:
    f_tmp.seek(offset)
    f_tmp.write(msg)

  f_tmp.close()

  return f_tmp

def assert_registers(state, **regs):
  for reg in cpu.registers.REGISTER_NAMES:
    if reg in ('flags', 'ip'):
      continue

    default = 0
    if reg in ('fp', 'sp'):
      default = 0x02DA

    elif reg in ('cs', 'ds'):
      default = 0x01

    val = regs.get(reg, default)

    assert getattr(state, reg) == val, 'Register %s expected to have value %s (%s), %s (%s) found instead' % (reg, mm.UINT16_FMT(val), val, mm.UINT16_FMT(getattr(state, reg)), getattr(state, reg))

def assert_flags(state, **flags):
  real_flags = cpu.registers.FlagsRegister()
  real_flags.from_uint16(state.flags)

  assert real_flags.privileged == flags.get('privileged', 1), 'PRIV flag expected to be %s' % flags.get('privileged', 1)
  assert real_flags.hwint == flags.get('hwint', 1), 'HWINT flag expected to be %s' % flags.get('hwint', 1)
  assert real_flags.e == flags.get('e', 0), 'E flag expected to be %s' % flags.get('e', 0)
  assert real_flags.z == flags.get('z', 0), 'Z flag expected to be %s' % flags.get('z', 0)
  assert real_flags.o == flags.get('o', 0), 'O flag expected to be %s' % flags.get('o', 0)
  assert real_flags.s == flags.get('s', 0), 'S flag expected to be %s' % flags.get('s', 0)

def assert_mm(state, **cells):
  for addr, expected_value in cells.items():
    addr = util.str2int(addr)
    expected_value = util.str2int(expected_value)
    page_index = mm.addr_to_page(addr)
    page_offset = mm.addr_to_offset(addr)

    for page in state.mm_page_states:
      if page.index != page_index:
        continue

      real_value = page.content[page_offset] | (page.content[page_offset + 1] << 8)
      assert real_value == expected_value, 'Value at %s (page %s, offset %s) should be %s, %s found instead' % (mm.ADDR_FMT(addr), page_index, mm.UINT8_FMT(page_offset), mm.UINT16_FMT(expected_value), mm.UINT16_FMT(real_value))
      break

    else:
      assert False, 'Page %i (address %s) not found in memory' % (page_index, mm.ADDR_FMT(addr))

def assert_file_content(filename, cells):
  with open(filename, 'rb') as f:
    for cell_offset, cell_value in cells.iteritems():
      f.seek(cell_offset)
      real_value = ord(f.read(1))
      assert real_value == cell_value, 'Value at %s (file %s) should be %s, %s found instead' % (cell_offset, filename, mm.UINT8_FMT(cell_value), mm.UINT8_FMT(real_value))

def run_machine(code, machine_config, coredump_file = None):
  M = machine.Machine()

  if not hasattr(util, 'CONSOLE') or util.CONSOLE is None:
    util.CONSOLE = console.Console(M, None, sys.stdout)
    util.CONSOLE.boot()

    util.CONSOLE.set_quiet_mode('VERBOSE' not in os.environ)

  M.hw_setup(machine_config)

  sections = cpu.assemble.translate_buffer(code)

  binary = machine.Binary('<dummy>')
  binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions = M.memory.load_raw_sections(sections)
  binary.ip = binary.symbols.get('main', mm.UInt16(0)).u16

  M.binaries.append(binary)

  M.boot()
  M.run()
  M.wait()

  state = core.VMState.capture_vm_state(M, suspend = False)

  if coredump_file:
    state.save(coredump_file)

  return state

def common_run_machine(code, machine_config = None, cpus = 1, cores = 1, irq_routines = 'instructions/interrupts-basic.bin'):
  if not machine_config:
    machine_config = config.MachineConfig()

  machine_config.add_section('machine')
  machine_config.set('machine', 'cpus', cpus)
  machine_config.set('machine', 'cores', cores)
  machine_config.set('machine', 'interrupt-routines', 'tests/instructions/interrupts-basic.bin')
  machine_config.add_section('cpu')
  machine_config.set('cpu', 'math-coprocessor', 'yes')

  return run_machine(code, machine_config)
