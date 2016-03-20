import difflib
import os.path
import subprocess
import sys

from testconfig import config
from functools import partial
from six import print_

tests_dir = partial(os.path.join, config['dirs']['tests'], 'compiler')
logs_dir  = partial(os.path.join, config['dirs']['logs'], 'compiler')

def run_compiler(label, file_in, file_out, options = None, diff_expected = None, exit_code = 0):
  options = options or []
  out = logs_dir('%s.out' % label)

  cmd = [
    config['vm-runner']['ducky-cc'],
    '-i %s' % file_in,
    '-o %s' % file_out,
    '-O0',
    '-q'
  ] + options

  env = os.environ.copy()

  if 'COVERAGE_FILE' in os.environ:
    cmd[0] = '%s %s' % (config['vm-runner']['coverage'], cmd[0])
    env['COVERAGE_FILE'] = os.path.join(config['dirs']['coverage'], '.coverage.compiler.%s' % label)

  cmd[0] = '%s %s' % (config['vm-runner']['runner'], cmd[0])

  with open(out, 'w') as f_out:
    try:
      subprocess.check_call(' '.join(cmd), stdout = f_out, stderr = f_out, shell = True, env = env)

    except subprocess.CalledProcessError as e:
      if exit_code != e.returncode:
        assert False, 'Compiler failed with exit code %s' % e.returncode

      return

    else:
      if exit_code != 0:
        assert False, 'Compiler failed with exit code 0'

  if diff_expected is None:
    return

  expected = tests_dir(*diff_expected)

  if not os.path.exists(expected):
    return

  with open(expected, 'r') as f_expected:
    with open(file_out, 'r') as f_actual:
      diff = '\n'.join(list(difflib.unified_diff(f_expected.readlines(), f_actual.readlines(), lineterm = '')))
      if diff:
        print_(diff, file = sys.stderr)
        assert False, 'Actual output does not match the expected.'

def common(name, **kwargs):
  run_compiler(name, tests_dir(name + '.c'), logs_dir(name + '.asm'), **kwargs)

def test_assign1():
  common('assign-1')

def test_assign2():
  common('assign-2')

def test_assign3():
  common('assign-3', exit_code = 1)

def test_assign4():
  common('assign-4', exit_code = 1)

def test_assign5():
  common('assign-5')

def test_assign6():
  common('assign-6')

def test_assign7():
  common('assign-7')

def test_assign8():
  common('assign-8')

def test_assign9():
  common('assign-9')

def test_assign10():
  common('assign-10', exit_code = 1)

def test_assign11():
  common('assign-11')

def test_assign12():
  common('assign-12')

def test_assign13():
  common('assign-13')

def test_assign14():
  common('assign-14')

def test_assign15():
  common('assign-15', exit_code = 1)

def test_assign16():
  common('assign-16')

def test_assign17():
  common('assign-17')

def test_assign18():
  common('assign-18')

def test_assign19():
  common('assign-19')

def test_hello_world():
  common('hello-world')

def test_hello_world_optimize():
  common('hello-world', options = ['-O 1'])
