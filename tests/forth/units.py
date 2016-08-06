from . import run_forth_vm, logs_dir, tests_dir
from .. import repeat

def __run_unit(iteration, name):
  options = [
    '--add-option=device-3:streams_in=%s' % tests_dir('forth', 'ans-testsuite', 'src', 'tester.fr'),
    '--add-option=device-3:streams_in=%s' % tests_dir('forth', 'units', '%s.f' % name)
  ]

  return run_forth_vm(out = logs_dir('forth-unit-%s.out.%d' % (name, iteration)), machine = logs_dir('forth-unit-%s.machine.%d' % (name, iteration)), options = options, diff_expected = ('forth', 'units', '%s.expected' % name), coverage_name = 'forth-unit-%s.%d' % (name, iteration))

@repeat('tests.forth.units.box', 'tests.forth.units', 'tests.forth')
def test_box(iteration):
  __run_unit(iteration, 'box')

@repeat('tests.forth.units.comparison', 'tests.forth.units', 'tests.forth')
def test_comparison(iteration):
  __run_unit(iteration, 'comparison')

@repeat('tests.forth.units.emit', 'tests.forth.units', 'tests.forth')
def test_emit(iteration):
  __run_unit(iteration, 'emit')

@repeat('tests.forth.units.env_query', 'tests.forth.units', 'tests.forth')
def test_env_query(iteration):
  __run_unit(iteration, 'env-query')

@repeat('tests.forth.units.fib', 'tests.forth.units', 'tests.forth')
def test_fib(iteration):
  __run_unit(iteration, 'fib')

@repeat('tests.forth.units.if', 'tests.forth.units', 'tests.forth')
def test_if(iteration):
  __run_unit(iteration, 'if')

@repeat('tests.forth.units.int', 'tests.forth.units', 'tests.forth')
def test_int(iteration):
  __run_unit(iteration, 'int')

@repeat('tests.forth.units.loop', 'tests.forth.units', 'tests.forth')
def test_loop(iteration):
  __run_unit(iteration, 'loop')

@repeat('tests.forth.units.number', 'tests.forth.units', 'tests.forth')
def test_number(iteration):
  __run_unit(iteration, 'number')

@repeat('tests.forth.units.sieve', 'tests.forth.units', 'tests.forth')
def test_sieve(iteration):
  __run_unit(iteration, 'sieve')

@repeat('tests.forth.units.stack', 'tests.forth.units', 'tests.forth')
def test_stack(iteration):
  __run_unit(iteration, 'stack')

@repeat('tests.forth.units.sumint', 'tests.forth.units', 'tests.forth')
def test_sumint(iteration):
  __run_unit(iteration, 'sum-int')

@repeat('tests.forth.units.welcome', 'tests.forth.units', 'tests.forth')
def test_welcome(iteration):
  __run_unit(iteration, 'welcome')
