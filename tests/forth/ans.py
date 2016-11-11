from . import run_forth_vm, logs_dir, tests_dir
from .. import repeat

ANS_TESTS = [
  'prelimtest.fth',
  'tester.fr',
  'core.fr',
  'coreplustest.fth',
  'utilities.fth',
  'errorreport.fth',
  'coreexttest.fth',
  'blocktest.fth',
  'doubletest.fth',
  'memorytest.fth'
]

@repeat('tests.forth.ans', 'tests.forth')
def test_ans(iteration):
  options = [
    ('--add-option=device-3:streams_in=%s' % tests_dir('forth', 'ans-testsuite', 'src', f)) for f in ANS_TESTS
  ] + [
    '--add-option=device-3:streams_in=%s' % tests_dir('forth', 'ans-report.f')
  ]

  return run_forth_vm(out = logs_dir('forth-ans.out.%d' % iteration), machine = logs_dir('forth-ans.machine.%d' % iteration), options = options, coverage_name = 'forth-ans', diff_expected = ('forth', 'ans.expected'))
