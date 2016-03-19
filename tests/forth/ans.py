from . import run_forth_vm, logs_dir, tests_dir

def test_ans():
  options = [
    ('--add-option=device-3:streams_in=%s' % tests_dir('forth', 'ans-testsuite', 'src', f)) for f in ['prelimtest.fth', 'tester.fr', 'core.fr', 'coreplustest.fth', 'utilities.fth', 'errorreport.fth']
  ] + ['--add-option=device-3:streams_in=%s' % tests_dir('forth', 'ans-report.f')]

  return run_forth_vm(out = logs_dir('forth-ans.out'), machine = logs_dir('forth-ans.machine'), options = options, coverage_name = 'forth-ans')
