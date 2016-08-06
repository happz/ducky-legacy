import os
import logging
import sys
import tempfile

from six import iteritems
from six.moves import range
from functools import wraps

import ducky.config
import ducky.cpu.assemble
import ducky.cpu.registers
import ducky.console
import ducky.log
import ducky.machine
import ducky.mm
import ducky.snapshot
import ducky.util

from ducky.util import F

from unittest import TestCase  # noqa

try:
  import unittest.mock as mock  # noqa

except ImportError:
  import mock  # noqa

from testconfig import config

LOGGER = logging.getLogger()

PYPY = hasattr(sys, 'pypy_version_info')
from six import PY2  # noqa
from six import PY3  # noqa


#
# Hypothesis setup
#
from hypothesis import settings

DEFAULT_EXAMPLES = 200

if 'HYPOTHESIS_PROFILE' in os.environ:
  profile = os.environ['HYPOTHESIS_PROFILE'].lower()

  if profile not in config['hypothesis']:
    LOGGER.warning('Unknown hypothesis profile "%s"', profile)
    profile = settings(max_examples = DEFAULT_EXAMPLES)

  else:
    profile = settings(max_examples = int(config['hypothesis'][profile]))

  settings.register_profile('ducky-profile', profile)

else:
  settings.register_profile('ducky-profile', settings(max_examples = DEFAULT_EXAMPLES))

settings.load_profile('ducky-profile')


def repeat(*test_paths):
  def wrap(fn):
    @wraps(fn)
    def wrapper():
      _test_paths = test_paths + ('tests',)

      for test_path in _test_paths:
        count = config.get('repeats', {}).get(test_path)
        if count is not None:
          count = int(count)
          break

      else:
        count = 1

      for n in range(count):
        yield (fn, n)

    return wrapper
  return wrap

def get_tempfile(keep = True):
  return tempfile.NamedTemporaryFile('w+b', delete = not keep, dir = os.getenv('TMPDIR'))

def prepare_file(size, messages = None, pattern = 0xDE):
  f_tmp = get_tempfile()

  # fill file with pattern
  f_tmp.seek(0)
  for _ in range(0, size):
    f_tmp.write(ducky.util.str2bytes(chr(pattern)))

  messages = messages or []

  # write out messages
  for offset, msg in messages:
    f_tmp.seek(offset)
    f_tmp.write(ducky.util.str2bytes(msg))

  f_tmp.close()

  return f_tmp

def assert_raises(callable, exc_class, message = ''):
  try:
    callable()

  except exc_class:
    pass

  else:
    assert False, message

def assert_registers(state, **regs):
  for reg in ducky.cpu.registers.REGISTER_NAMES:
    if reg in ('flags', 'ip', 'cnt'):
      continue

    val = regs.get(reg, 0)

    reg_index = ducky.cpu.registers.REGISTER_NAMES.index(reg)
    reg_value = state.registers[reg_index]

    assert reg_value == val, F('Register {reg} expected to have value {expected} ({expected:L}), {actual} ({actual:L}) found instead', reg = reg, expected = val, actual = reg_value)

def assert_flags(state, **flags):
  core_flags = ducky.cpu.CoreFlags.from_int(state.flags)

  flag_labels = {
    'privileged': 'privileged',
    'hwint':      'hwint_allowed',
    'e':          'equal',
    'z':          'zero',
    'o':          'overflow',
    's':          'sign'
  }

  for short_flag, core_flag in iteritems(flag_labels):
    passed = flags.get(short_flag, True if short_flag == 'privileged' else False)
    expected = True if passed in (True, 1) else False
    actual = getattr(core_flags, core_flag)

    assert expected == actual, F('Flag {flag} expected to be {expected}, {actual} found instead', flag = core_flag, expected = expected, actual = actual)

def assert_mm(state, cells):
  for addr, expected_value in cells:
    addr = addr
    expected_value = expected_value
    page_index = ducky.mm.addr_to_page(addr)
    page_offset = ducky.mm.addr_to_offset(addr)

    for page in state.get_page_states():
      if page.index != page_index:
        continue

      real_value = page.content[page_offset] | (page.content[page_offset + 1] << 8) | (page.content[page_offset + 2] << 16) | (page.content[page_offset + 3] << 24)
      assert real_value == expected_value, 'Value at {} (page {}, offset {}) should be {}, {} found instead'.format(ducky.mm.ADDR_FMT(addr), page_index, ducky.mm.UINT8_FMT(page_offset), ducky.mm.UINT32_FMT(expected_value), ducky.mm.UINT32_FMT(real_value))
      break

    else:
      assert False, 'Page {} (address {}) not found in memory'.format(page_index, ducky.mm.ADDR_FMT(addr))

def assert_mm_pages(state, *pages):
  pg_indices = [pg.index for pg in state.get_page_states()]

  for pg_id in pages:
    assert pg_id in pg_indices, 'Page {} not found in VM state'.format(pg_id)

def assert_file_content(filename, cells):
  with open(filename, 'rb') as f:
    for cell_offset, cell_value in iteritems(cells):
      f.seek(cell_offset)
      real_value = ord(f.read(1))
      assert real_value == cell_value, 'Value at {} (file {}) should be {}, {} found instead'.format(cell_offset, filename, ducky.mm.UINT8_FMT(cell_value), ducky.mm.UINT8_FMT(real_value))

def common_asserts(M, S, mm_asserts = None, file_asserts = None, **kwargs):
  mm_asserts = mm_asserts or {}
  file_asserts = file_asserts or []

  assert_registers(S.get_child('machine').get_child('cpu0').get_child('core0'), **kwargs)
  assert_flags(S.get_child('machine').get_child('cpu0').get_child('core0'), **kwargs)

  assert_mm(S.get_child('machine').get_child('memory'), mm_asserts)

  for filename, cells in file_asserts:
    assert_file_content(filename, cells)

def compile_code(code):
  f_asm = get_tempfile()
  f_asm.write(ducky.util.str2bytes(code))
  f_asm.flush()
  f_asm.close()

  f_obj_name = os.path.splitext(f_asm.name)[0] + '.o'
  f_bin_name = os.path.splitext(f_asm.name)[0] + '.testbin'

  os.system('PYTHONPATH={} {} -f -I {} -i {} -o {}'.format(os.getenv('PYTHONPATH'), os.getenv('DAS'), os.getenv('TOPDIR'), f_asm.name, f_obj_name))
  os.system('PYTHONPATH={} {} -f -i {} -o {} --section-base=.text=0x0000'.format(os.getenv('PYTHONPATH'), os.getenv('DLD'), f_obj_name, f_bin_name))

  os.unlink(f_asm.name)
  os.unlink(f_obj_name)

  return f_bin_name

def run_machine(code = None, binary = None, machine_config = None, coredump_file = None, pokes = None, post_setup = None, post_boot = None, post_run = None, logger = None, **kwargs):
  pokes = pokes or []
  post_setup = post_setup or []
  post_boot = post_boot or []
  post_run = post_run or []

  logger = logger or ducky.log.create_logger(name = 'ducky-test', level = logging.DEBUG)

  M = ducky.machine.Machine(logger = logger)

  if os.getenv('VMDEBUG') == 'yes':
    M.LOGGER.setLevel(logging.DEBUG)

  if binary is None and code is not None:
    binary = compile_code(code)

  if binary is not None:
    machine_config.add_section('bootloader')
    machine_config.set('bootloader', 'file', binary)

  M.hw_setup(machine_config)

  if not all(fn(M) in (True, None) for fn in post_setup):
    if code is not None:
      os.unlink(binary)

    return M

  M.boot()

  if code is not None:
    os.unlink(binary)

  if not all(fn(M) in (True, None) for fn in post_boot):
    return M

  for address, value, length in pokes:
    M.rom_loader.poke(address, value, length)

  M.run()

  for fn in post_run:
    fn(M, M.last_state)

  return M

def common_run_machine(code = None, binary = None, machine_config = None,
                       cpus = 1, cores = 1,
                       pokes = None,
                       storages = None,
                       mmaps = None,
                       post_setup = None, post_boot = None, post_run = None,
                       logger = None,
                       **kwargs):
  storages = storages or []
  mmaps = mmaps or []

  if code is not None and isinstance(code, list):
    code = '\n'.join(code)

  machine_config = machine_config or ducky.config.MachineConfig()

  if not machine_config.has_section('machine'):
    machine_config.add_section('machine')

  machine_config.set('machine', 'cpus', cpus)
  machine_config.set('machine', 'cores', cores)

  if not machine_config.has_section('cpu'):
    machine_config.add_section('cpu')

  machine_config.set('cpu', 'math-coprocessor', 'yes')

  if storages:
    machine_config.add_device('bio', 'ducky.devices.storage.BlockIO')

    for driver, id, path in storages:
      machine_config.add_storage(driver, id, filepath = path)

  for path, addr, size, offset, access, shared in mmaps:
    machine_config.add_mmap(path, addr, size, offset = offset, access = access, shared = shared)

  return run_machine(code = code, binary = binary, machine_config = machine_config, post_setup = post_setup, post_boot = post_boot, post_run = post_run, pokes = pokes, logger = logger)
