import difflib
import os.path
import subprocess
import sys

from testconfig import config
from functools import partial
from six import print_, iteritems

tests_dir = partial(os.path.join, config['dirs']['tests'])
forth_dir = partial(os.path.join, config['dirs']['forth'])
logs_dir  = partial(os.path.join, config['dirs']['logs'], 'forth')

def run_forth_vm(out = None, machine = None, options = None, diff_expected = None, coverage_name = None):
  options = options or []

  cmd = [
    config['vm-runner']['ducky-vm'],
    '-g',
    '--machine-config=%s' % tests_dir('forth', 'machine.conf'),
    '--set-option=bootloader:file=%s' % forth_dir('ducky-forth'),
    '--set-option=device-3:streams_in=%s' % tests_dir('forth', 'enable-test-mode.f'),
    '--add-option=device-3:streams_in=%s' % forth_dir('ducky-forth.f')
  ] + options + [
    '--set-option=device-3:stream_out=%s' % out
  ]

  env = os.environ.copy()

  if config['options']['coverage'] == 'yes':
    assert coverage_name is not None

    cmd[0] = '%s %s' % (config['vm-runner']['coverage'], cmd[0])
    env['COVERAGE_FILE'] = os.path.join(config['dirs']['coverage'], '.coverage.%s' % coverage_name)

  if config['options']['profile'] == 'yes':
    cmd.append('-p -P %s' % config['dirs']['profile'])

  if os.environ.get('JIT', 'no') == 'yes':
    cmd.append('--jit')

  cmd[0] = '%s %s' % (config['vm-runner']['runner'], cmd[0])

  cmd = ' '.join(cmd)

  with open(config['log']['trace'], 'a') as f_trace:
    f_trace.write('CMD: %s\n' % cmd)
    f_trace.write('ENV:\n')
    for k, v in iteritems(env):
      f_trace.write('   %s=%s\n' % (k, v))

  with open(machine, 'w') as f_out:
    try:
      subprocess.check_call(cmd, stdout = f_out, stderr = f_out, shell = True, env = env)

    except subprocess.CalledProcessError as e:
      assert False, 'FORTH VM failed with exit code %s' % e.returncode

  with open(out, 'r') as f_out:
    output = f_out.read()

  if 'INCORRECT RESULT' in output or 'WRONG NUMBER OF RESULTS' in output:
    print_(output, file = sys.stderr)
    assert False, 'Test provided incorrect results'

  if diff_expected is None:
    return

  expected = tests_dir(*diff_expected)

  if not os.path.exists(expected):
    return

  with open(expected, 'r') as f_expected:
    with open(out, 'r') as f_actual:
      diff = '\n'.join(list(difflib.unified_diff(f_expected.readlines(), f_actual.readlines(), lineterm = '')))
      if diff:
        print_(diff, file = sys.stderr)
        assert False, 'Actual output does not match the expected.'
