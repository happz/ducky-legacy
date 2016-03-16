from . import run_forth_vm, logs_dir, tests_dir

def __run_unit(name):
  options = [
    '--add-option=device-3:streams_in=%s' % '/data/virtualenv/ducky-2.7/ducky/tests/forth/ans-testsuite/src/tester.fr',
    '--add-option=device-3:streams_in=%s' % tests_dir('forth', 'units', '%s.f' % name),
    '--add-option=device-3:streams_in=%s' % tests_dir('forth', 'run-test-word.f'),
  ]

  return run_forth_vm(out = logs_dir('forth-unit-%s.out' % name), machine = logs_dir('forth-unit-%s.machine' % name), options = options, diff_expected = tests_dir('units', '%s.expected' % name), coverage_name = 'forth-unit-%s' % name)

def test_box():
  __run_unit('box')

def test_comparison():
  __run_unit('comparison')

def test_emit():
  __run_unit('emit')

def test_env_query():
  __run_unit('env-query')

def test_fib():
  __run_unit('fib')

def test_if():
  __run_unit('if')

def test_int():
  __run_unit('int')

def test_loop():
  __run_unit('loop')

def test_number():
  __run_unit('number')

def test_stack():
  __run_unit('stack')

def test_welcome():
  __run_unit('welcome')
