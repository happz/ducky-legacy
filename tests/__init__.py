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
  for i in range(0, cpu.registers.Registers.FLAGS):
    reg = 'r%i' % i
    val = regs.get(reg, 0)
    assert getattr(state, reg) == val, 'Register %s expected to have value %s, %s found instead' % (reg, val, getattr(state, reg))

def assert_flags(state, privileged = 1, e = 0, z = 0, o = 0, s = 0):
  assert state.flags.flags.privileged == privileged, 'PRIV flag expected to be %s' % privileged
  assert state.flags.flags.e == e, 'E flag expected to be %s' % e
  assert state.flags.flags.z == z, 'Z flag expected to be %s' % z
  assert state.flags.flags.o == o
  assert state.flags.flags.s == s

def run_machine(code, coredump_file = None, **kwargs):
  M = machine.Machine()

  if not hasattr(util, 'CONSOLE'):
    util.CONSOLE = console.Console(M, None, open('/dev/null', 'wb'))
    util.CONSOLE.boot()
    util.CONSOLE.set_verbosity(0)

  M.hw_setup(**kwargs)

  sections = cpu.assemble.translate_buffer(code)

  csr, dsr, sp, ip, symbols = M.memory.load_raw_sections(sections)
  M.init_states.append((csr, dsr, sp, ip, False))
  M.binaries.append((csr, dsr, sp, ip, symbols))

  M.boot()
  M.run()
  M.wait()

  state = core.VMState.capture_vm_state(M)

  if coredump_file:
    state.save(coredump_file)

  return state

common_machine_run = functools.partial(run_machine, cpus = 1, cores = 1, irq_routines = 'instructions/interrupts-basic.bin')

