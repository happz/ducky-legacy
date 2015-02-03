import patch

import functools
import os
import sys
import unittest

import cpu.assemble
import cpu.registers
import console
import core
import machine
import mm
import util

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
  assert state.flags.flags.privileged == flags.get('privileged', 1), 'PRIV flag expected to be %s' % flags.get('privileged', 1)
  assert state.flags.flags.e == flags.get('e', 0), 'E flag expected to be %s' % flags.get('e', 0)
  assert state.flags.flags.z == flags.get('z', 0), 'Z flag expected to be %s' % flags.get('z', 0)
  assert state.flags.flags.o == flags.get('o', 0), 'O flag expected to be %s' % flags.get('o', 0)
  assert state.flags.flags.s == flags.get('s', 0), 'S flag expected to be %s' % flags.get('s', 0)

def assert_mm(state, **cells):
  for addr, expected_value in cells.items():
    addr = util.str2int(addr)
    expected_value = util.str2int(expected_value)
    page_index = mm.addr_to_page(addr)
    page_offset = mm.addr_to_offset(addr)

    for page in state.mm_page_states:
      if page.index != page_index:
        continue

      real_value = mm.buff_to_uint16(page.content, page_offset)
      assert real_value.u16 == expected_value, 'Value at %s (page %s, offset %s) should be %s, %s found instead' % (mm.ADDR_FMT(addr), page_index, mm.UINT8_FMT(page_offset), mm.UINT16_FMT(expected_value), mm.UINT16_FMT(real_value))
      break

    else:
      assert False, 'Page %i (address %s) not found in memory' % (page_index, mm.ADDR_FMT(addr))

def run_machine(code, coredump_file = None, **kwargs):
  M = machine.Machine()

  if not hasattr(util, 'CONSOLE'):
    util.CONSOLE = console.Console(M, None, sys.stdout)
    util.CONSOLE.boot()

    util.CONSOLE.set_quiet_mode('VERBOSE' not in os.environ)

  M.hw_setup(**kwargs)

  sections = cpu.assemble.translate_buffer(code)

  binary = machine.Binary('<dummy>')
  binary.cs, binary.ds, binary.sp, binary.ip, binary.symbols, binary.regions = M.memory.load_raw_sections(sections)
  binary.ip = binary.symbols.get('main', mm.UInt16(0))

  M.binaries.append(binary)

  M.boot()
  M.run()
  M.wait()

  state = core.VMState.capture_vm_state(M, suspend = False)

  if coredump_file:
    state.save(coredump_file)

  return state

common_machine_run = functools.partial(run_machine, cpus = 1, cores = 1, irq_routines = 'instructions/interrupts-basic.bin')

