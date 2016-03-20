#! /usr/bin/env python

"""
Master of the build system, root of all scons files, The One file.

In this files all necessary helpers are defined, to let me simplify
``SConscript`` files in directories as much as possible.
"""

import atexit
import collections
import colorama
import datetime
import fnmatch
import hashlib
import os
import subprocess
import sys

from functools import partial
from six import print_, iteritems, string_types

#
# Our extra options
#
# These have to be first - well, at least --no-color has to be first,
# and it makes no sense to put that one here and the rest somewhere bellow.
#

def generate_build_stamp():
  return subprocess.check_output('git log --date=iso --pretty=format:"%H %cd" -n 1 | cut -d" " -f1,2,3 | tr -d "-" | tr -d ":" | tr " " "-"', shell = True).strip()

AddOption('--no-color',
          dest = 'no_color',
          action = 'store_true',
          default = False,
          help = 'Do not colorize output')

AddOption('--testset-id',
          dest = 'testset_id',
          action = 'store',
          type = int,
          default = os.getpid(),
          metavar = 'ID',
          help = 'Set testset id to this value')

AddOption('--testset-dir',
          dest = 'testset_dir',
          action = 'store',
          metavar = 'NAME',
          help = 'Store test results in this test set')

AddOption('--with-jit',
          dest = 'jit',
          action = 'store_true',
          default = False,
          help = 'Run with JIT enabled')

AddOption('--with-mmap',
          dest = 'mmap',
          action = 'store_true',
          default = False,
          help = 'Run using mmap as binary loading method.')

AddOption('--with-coverage',
          dest = 'coverage',
          action = 'store_true',
          default = False,
          help = 'Run tests with coverage enabled')

AddOption('--with-profiling',
          dest = 'profiling',
          action = 'store_true',
          default = False,
          help = 'Run tests with profiling enabled')

AddOption('--pass-testsuite-output',
          dest = 'pass_testsuite_output',
          action = 'store_true',
          default = False,
          help = 'If set, output of testsuites will be passed directly to stdout/stderr')

AddOption('--hypothesis-profile',
          dest = 'hypothesis_profile',
          action = 'store',
          default = 'Default',
          metavar = 'PROFILE',
          help = 'Set Hypothesis profile to PROFILE')

AddOption('--clean-testsets',
          dest = 'clean_testsets',
          action = 'store_true',
          default = False,
          help = 'Remove testset dirs when building "clean" target.')

VARS = Variables(None, ARGUMENTS)
VARS.Add(             'BUILD_STAMP',        'Set to force FORTH kernel build stamp', generate_build_stamp())
VARS.Add(BoolVariable('BOOT_IMAGE',         'Set to true to build boot loader with support for Ducky images', True))
VARS.Add(BoolVariable('FORTH_DEBUG',        'Build FORTH kernel with debugging enabled', False))
VARS.Add(BoolVariable('FORTH_DEBUG_FIND',   'Build FORTH kernel with FIND debugging enabled', False))
VARS.Add(BoolVariable('FORTH_TIR',          'Build FORTH kernel with TOS in register', True))

#
# Output colorization
#
# Turned on by default, if --no-color is set, declare relevant helpers
# as NOPs.
#
if GetOption('no_color') is False:
  def colorize(fg, bg, s):
    """
    Returns colorized version of input string.
    """

    fg = getattr(colorama.Fore, fg) if fg is not None else ''
    bg = getattr(colorama.Back, bg) if bg is not None else ''

    return '%s%s%s%s' % (fg, bg, s, colorama.Style.RESET_ALL)

  def colorize_fmt(s):
    fgs = [
      ('${GREEN}', colorama.Fore.GREEN),
      ('${BLUE}',  colorama.Fore.BLUE),
      ('${CLR}',   colorama.Style.RESET_ALL),
    ]

    for p, c in fgs:
      s = s.replace(p, c)

    return s

  GREEN  = partial(colorize, 'GREEN',  None)
  YELLOW = partial(colorize, 'YELLOW', None)
  RED    = partial(colorize, 'RED',    None)
  BLUE   = partial(colorize, 'BLUE',   None)

else:
  def colorize(fg, bg, s):
    return s

  def colorize_fmt(s):
    return s

  def BLUE(s):
    return s

  GREEN = YELLOW = RED = BLUE


#
# Extra Environment methods
#
def __is_silent(self):
  """
  Returns ``True`` if ``-s`` option is set.
  """

  return self.GetOption('silent')

def __DEBUG(self, msg):
  if not self.IS_SILENT():
    print_('[DEBUG] %s' % msg)

def __PASS(self, runtime = None):
  msg = 'PASS'

  if self is not None and not self.IS_SILENT():
    msg = '[' + msg + ']'

  if runtime is not None:
    msg += ' (%s)' % str(runtime)

  print_(GREEN(msg))

def __FAIL(self):
  if self.IS_SILENT():
    print_(RED('FAIL'))

  else:
    print_(RED('[FAIL]'))

def __WORK(self, label, target):
  if self.IS_SILENT():
    print_('%s %s ... ' % (YELLOW('[' + label + ']'), target), end = '', flush = True)

  else:
    print_('%s %s' % (YELLOW('[' + label + ']'), target), flush = True)

def __on_clean(self, target):
  if self.GetOption('clean'):
    self.Default(target)

def __pass_var_as_define(self, name, to_boolean = True, ignore_false = True):
  if name not in self:
    return

  if ignore_false and not self[name]:
    return

  if to_boolean:
    value = 'yes' if self[name] else 'no'
  else:
    value = str(self[name])

  self.Append(DEFINES = ['-D %s=%s' % (name, value)])

def __run_something(_env, label, target, runner, *args, **kwargs):
  expected_exit = 0
  if 'expected_exit' in kwargs:
    expected_exit = kwargs['expected_exit']
    del kwargs['expected_exit']

  _env.DEBUG('__run_something: label="%s", target="%s"' % (label, target))
  _env.DEBUG('    runner="%s"' % runner)
  _env.DEBUG('    expected_exit=%d' % expected_exit)
  _env.DEBUG('    args="%s"' % ', '.join(['"%s"' % str(arg) for arg in args]))
  _env.DEBUG('    kwargs="%s"' % ', '.join(['%s="%s"' % (k, v) for k, v in iteritems(kwargs)]))

  _env.WORK(label, target)

  start = datetime.datetime.now()

  def __PASS():
    _env.PASS(runtime = datetime.datetime.now() - start)

    return 0

  def __FAIL(exit_code):
    _env.FAIL()
    return 1

  try:
    runner(*args, **kwargs)

  except subprocess.CalledProcessError as e:
    if e.returncode == expected_exit:
      return __PASS()

    return __FAIL(e.returncode)

  except Exception as e:
    import traceback

    tb = traceback.format_exc()

    _env.FAIL()
    _env.ERROR(str(e))

    for l in tb.split('\n'):
      _env.ERROR(l)

    return 1

  else:
    if expected_exit == 0:
      return __PASS()

    return __FAIL(0)

class DuckyCommand(object):
  def __init__(self, _env, env = None, runner = None, command = None, stdout = None, stderr = None, junit_record = None):
    self.env     = env or {}
    self.runner  = runner if runner is not None else _env['PYTHON']
    self.command = command if command is not None else ''

    self.stdout  = stdout
    self.stderr  = stderr

    self.junit_record = junit_record

  def materialize(self, env):
    env.DEBUG('materialize:')
    env.DEBUG('  runner="%s"' % self.runner)
    env.DEBUG('  command="%s"' % self.command)
    env.DEBUG('  stdout=%s' % self.stdout)
    env.DEBUG('  stderr=%s' % self.stderr)

    cmd = [
      self.runner,
      self.command
    ]

    kwargs = {
      'shell': True,
      'env':   dict(env['ENV'], **self.env)
    }

    if self.stdout is None:
      kwargs['stdout'] = sys.stdout

      if self.stderr is None:
        kwargs['stderr'] = sys.stderr

      else:
        cmd.append('2> %s' % self.stderr)

    else:
      if self.stderr is None:
        cmd.append('> %s' % self.stdout)
        kwargs['stderr'] = sys.stderr

      else:
        if self.stdout == self.stderr:
          cmd.append('&> %s' % self.stdout)

        else:
          cmd.append('> %s' % self.stdout)
          cmd.append('2> %s' % self.stderr)

    return ' '.join(cmd), kwargs

  def run(self, env, label, message, expected_exit = 0):
    cmd, kwargs = self.materialize(env)

    return env.RunSomething(label, message, subprocess.check_call, cmd, expected_exit = expected_exit, **kwargs)

  def wrap_by_coverage(self, env):
    self.env['COVERAGE_FILE'] = env.subst('$COVERAGEDIR/.coverage.' + hashlib.sha256(self.command.replace(' ', '-').replace('/', '-')).hexdigest())
    self.runner = self.runner + ' ' + env.subst('$VIRTUAL_ENV/bin/coverage run --rcfile=$TOPDIR/coveragerc')

  def wrap_by_profiling(self, env):
    self.command += ' ' + env.subst('-p -P $PROFILEDIR')

def __compile_ducky_object(source, target, env):
  cmd = DuckyCommand(env)
  cmd.command = env.subst('$VIRTUAL_ENV/bin/ducky-as {inputs} {defines} {includes} -o {target}'.format(
    inputs   = ' '.join(['-i %s' % f for f in source]),
    defines  = ' '.join(env['DEFINES']) if 'DEFINES' in env else '',
    includes = ' '.join(env['INCLUDES']) if 'INCLUDES' in env else '',
    target   = target[0]))

  if 'COVERAGEDIR' in env:
    cmd.wrap_by_coverage(env)

  if GetOption('mmap') is True:
    cmd.command += ' --mmapable-sections'

  return cmd.run(env, 'COMPILE', target[0])

def __link_ducky_binary(source, target, env):
  cmd = DuckyCommand(env)
  cmd.command = env.subst('$VIRTUAL_ENV/bin/ducky-ld {inputs} {section_bases} -o {target}'.format(
    inputs = ' '.join(['-i %s' % f for f in source]),
    section_bases = ' '.join(['--section-base=%s' % section_base for section_base in env['SECTION_BASES']]) if 'SECTION_BASES' in env else '',
    target  = target[0]))

  if 'COVERAGEDIR' in env:
    cmd.wrap_by_coverage(env)

  return cmd.run(env, 'LINK', target[0])

def __run_ducky_binary(self, config, set_options = None, goon = True, expected_exit = 0):
  set_options = set_options or []

  def _run_ducky_binary(target, source, env, cmd = None, expected_exit = 0):
    assert cmd is not None

    return cmd.run(env, 'RUN', target[0], expected_exit = expected_exit)

  config = File(config) if isinstance(config, string_types) else config

  cmdline = self.subst('$VIRTUAL_ENV/bin/ducky-vm --machine-config={machine_config} {goon} {set_options}'.format(
    machine_config = config.abspath,
    goon = '-g' if goon is True else '',
    set_options = ' '.join(['--set-option=%s' % option for option in set_options])))

  cmd = DuckyCommand(self)
  cmd.command = cmdline

  if 'COVERAGEDIR' in self:
    cmd.wrap_by_coverage(self)

  if 'PROFILEDIR' in self:
    cmd.wrap_by_profiling(self)

  if GetOption('jit'):
    cmd.env['JIT'] = 'yes'

  return partial(_run_ducky_binary, cmd = cmd, expected_exit = expected_exit)

def __create_ducky_image(self, _target, _source, mode = 'binary', bio = False):
  def _create_ducky_image(target, source, env, cmd = None):
    assert cmd is not None

    return cmd.run(env, 'IMAGE', target[0])

  _source = File(_source) if isinstance(_source, string_types) else _source
  _target = File(_target) if isinstance(_target, string_types) else _target

  cmd = DuckyCommand(self)
  cmd.command = self.subst('$VIRTUAL_ENV/bin/ducky-img {mode} -i {source} -o {target} {bio}'.format(mode = '-b' if mode == 'binary' else '-h', source = _source.abspath, target = _target.abspath, bio = '--bio' if bio else ''))

  if 'COVERAGEDIR' in self:
    cmd.wrap_by_coverage(self)

  return partial(_create_ducky_image, cmd = cmd)

def __clone_env(self, *args, **kwargs):
  clone = self.Clone(*args, **kwargs)

  original_help = clone.Help

  def Help(self, s, **kwargs):
    return original_help(colorize_fmt(s), **kwargs)

  methods = {
    'IS_SILENT': __is_silent,
    'DEBUG':     __DEBUG,
    'INFO':      lambda self, msg: print_('%s %s' % (GREEN('[INFO]'), msg)),
    'WARN':      lambda self, msg: print_('%s %s' % (RED('[WARN]'), msg)),
    'ERROR':     lambda self, msg: print_('%s %s' % (RED('[ERR]'), msg)),
    'FAIL':      __FAIL,
    'PASS':      __PASS,
    'WORK':      __WORK,
    'OnClean':   __on_clean,
    'PassVarAsDefine': __pass_var_as_define,
    'FullClone':       __clone_env,

    # Virtual builders
    'RunSomething':    __run_something,
    'DuckyRun':        __run_ducky_binary,
    'DuckyImage':      __create_ducky_image,
    'GetDuckyDefine':  lambda self, *names: [os.path.join(str(ENV['DEFSDIR']), name + '.asm') for name in names]
  }

  for name, fn in iteritems(methods):
    AddMethod(clone, fn, name)

  clone.AddMethod(Help)

  return clone

def print_info(source, target, env):
  env.INFO('Build stamp:           %s' % env['BUILD_STAMP'])
  env.INFO('SCONS is using Python: %s (%s)' % (ENV['SCONS_PYTHON'], ENV['SCONS_PYTHON_NAME']))
  env.INFO('Default Python:        %s (%s)' % (ENV['PYTHON'], ENV['PYTHON_NAME']))

  if 'TESTSETDIR' in env:
    env.INFO('Test set dir:          %s' % ENV['TESTSETDIR'])
    env.INFO('Results dir:           %s' % ENV['RESULTSDIR'])
    env.INFO('Log dir:               %s' % ENV['LOGDIR'])
    env.INFO('Tmp dir:               %s' % ENV['TMPDIR'])
    env.INFO('Report dir:            %s' % ENV['REPORTDIR'])

    if 'COVERAGEDIR' in ENV:
      env.INFO('Coverage dir:          %s' % ENV['COVERAGEDIR'])

    if 'PROFILEDIR' in ENV:
      env.INFO('Profile dir:           %s' % ENV['PROFILEDIR'])

def build_failure_to_str(bf):
  import SCons.Errors

  if bf is None:
    return 'unknown target'

  if isinstance(bf, SCons.Errors.StopError):
    return str(bf)

  if bf.node:
    return str(bf.node) + ': ' + bf.errstr

  if bf.filename:
    return bf.filename + ': ' + bf.errstr

  return 'unknown failure: ' + bf.errstr

def build_status():
  from SCons.Script import GetBuildFailures

  bf = GetBuildFailures()
  if bf:
    return ('failed', ['Failed building %s' % build_failure_to_str(x) for x in bf if x is not None])

  return ('passed', None)

def display_build_status():
  status, messages = build_status()

  if messages is not None:
    print_('\n'.join([RED(msg) for msg in messages]))

def print_help(env, target, source):
  import SCons
  print_(SCons.Script.help_text)

def run_flake(target, source, env):
  def __find_files(d, pattern):
    files = []

    for root, dirnames, filenames in os.walk(d.abspath):
      if 'vhdl' in root:
        continue

      files += [os.path.join(root, f) for f in os.listdir(root) if fnmatch.fnmatch(f, pattern)]

    return files

  sources  = __find_files(Dir('#ducky'), '*.py')
  sources += __find_files(Dir('#tests'), '*.py')

  cmd = DuckyCommand(env, runner = '')
  cmd.command = 'flake8 --config={config_file} {files}'.format(
    config_file = File('#flake8.cfg').abspath,
    files = ' '.join(sources)
  )

  return cmd.run(env, 'INFO', 'flake')

DuckyObject = Builder(action = __compile_ducky_object)
DuckyBinary = Builder(action = __link_ducky_binary)


#
# Master Environment
#
# This is a template for all envs that come after it.
#
DEFSDIR = Dir('#defs')

ENV = Environment(
  variables = VARS,

  # Our special builders for Ducky files
  BUILDERS = {
    'DuckyObject': DuckyObject,
    'DuckyBinary': DuckyBinary
  },

  # Initial, quite empty environment
  ENV = {
    'PATH': os.environ['PATH']
  },

  # Directory with Ducky-supplied define files
  DEFSDIR  = DEFSDIR,
  INCLUDES = ['-I %s' % DEFSDIR.abspath],

  # Top-level directory of this Ducky repository
  TOPDIR = Dir('#.').abspath,

  # Path do current virtual environment - if any, empty string otherwise
  VIRTUAL_ENV = os.environ.get('VIRTUAL_ENV', ''),

  # Python version running scons
  SCONS_PYTHON = sys.executable,
  SCONS_PYTHON_NAME = sys.version.replace('\n', ' '),
  SCONS_PYTHON_VERSION = sys.version_info,

  # Python version provided by virtualenv
  PYTHON = subprocess.check_output('type python', shell = True).split('\n')[0].split(' ')[2].strip(),
  PYTHON_NAME = subprocess.check_output('python -c "from __future__ import print_function; import sys; print(sys.version)"', shell = True).replace('\n', ' ').strip(),
  PYTHON_VERSION = eval(subprocess.check_output('python -c "from __future__ import print_function; import sys; print(list(sys.version_info))"', shell = True))
)

# Clone ENV to ENV, to add our methods
ENV = __clone_env(ENV)

# Default target - if user asks for nothing specific, show him help.
ENV.Default(ENV.Command('default', None, print_help))

if COMMAND_LINE_TARGETS:
  targets = COMMAND_LINE_TARGETS

else:
  targets = DEFAULT_TARGETS

if len(targets) != 1:
  ENV.ERROR('Please, specify 1 target only')
  ENV.Exit(1)

ENV.Append(BUILD_TARGET = str(targets[0]))

if ENV['BUILD_TARGET'].startswith('tests'):
  if GetOption('testset_dir') is None:
    ENV.ERROR('For running tests, it is necessary to set --testset-dir option correctly.')
    Exit(1)

  testset_dir = 'tests-%s' % GetOption('testset_dir')
  testset_id = str(GetOption('testset_id'))
  testset_dir = os.path.join(Dir('#' + testset_dir).abspath, testset_id)

  ENV = ENV.FullClone(
    RAW_TESTSETDIR = GetOption('testset_dir'),
    TESTSETDIR  = testset_dir,
    TESTSETID   = testset_id,

    LOGDIR      = os.path.join(testset_dir, 'log'),
    RESULTSDIR  = os.path.join(testset_dir, 'results'),
    TMPDIR      = os.path.join(testset_dir, 'tmp'),
    CONFIGDIR   = os.path.join(testset_dir, 'config'),
    REPORTDIR   = os.path.join(testset_dir, 'report'),
    SNAPSHOTDIR = os.path.join(testset_dir, 'snapshot'),
    EXAMPLESDIR = Dir('examples').abspath,
    LOADERDIR   = Dir('boot').abspath
  )

  if GetOption('coverage') is True:
    ENV.Append(COVERAGEDIR = os.path.join(testset_dir, 'coverage'))

  if GetOption('profiling') is True:
    ENV.Append(PROFILEDIR  = os.path.join(testset_dir, 'profile'))

  ENV['ENV']['TESTSETDIR'] = ENV['TESTSETDIR']
  ENV['ENV']['TMPDIR']     = ENV['TMPDIR']

  print_info(None, None, ENV)

else:
  if GetOption('coverage') is True:
    ENV.Append(COVERAGEDIR = Dir('coverage').abspath)
    ENV.Command(ENV['COVERAGEDIR'], None, Mkdir(ENV['COVERAGEDIR']))

  if GetOption('profiling') is True:
    ENV.Append(PROFILEDIR  = Dir('profile').abspath)
    ENV.Command(ENV['PROFILEDIR'], None, Mkdir(ENV['PROFILEDIR']))


Export('ENV', 'GREEN', 'RED', 'DuckyCommand')

ENV.Help("""
  ${GREEN}Available targets:${CLR}
""")

# Generic info and usefull stuff
ENV.Command('info', None, print_info)
ENV.Help("""     ${BLUE}'scons info'${CLR} to gather information about environment,\n""")

# Defines
SConscript(os.path.join('defs', 'SConscript'))

# FORTH
SConscript(os.path.join('forth', 'SConscript'))

# Boot loaders
SConscript(os.path.join('boot', 'SConscript'))

# Examples
SConscript(os.path.join('examples', 'SConscript'))

# Tests
SConscript(os.path.join('tests', 'SConscript'))

# Utilities
ENV.Alias('flake', ENV.Command('.flake', None, run_flake))

# Documentation
ENV.Command('docs/introduction.rst', 'README.rst', 'cp README.rst docs/introduction.rst')
ENV.Command('.docs-generate', 'docs/introduction.rst', 'sphinx-apidoc -T -e -o docs/ ducky/')
ENV.AlwaysBuild('.docs-generate')
ENV.Command('.docs-html', '.docs-generate', 'make -C docs/ html')
ENV.AlwaysBuild('.docs-html')
ENV.Alias('docs', '.docs-html')

# And finalize help
ENV.Help("""
  ${GREEN}Utilities:${CLR}
     ${BLUE}'scons flake'${CLR} to run flake8 utility, and check for violations of Python
         style conventions,
     ${BLUE}'scons docs'${CLR} to generate documentation,

  or ${BLUE}'scons -h'${CLR} to see this help.

  ${GREEN}Available options:${CLR}

    --no-color                  Do not colorize output.
    --testset=NAME              Store test results in this test set.
    --with-coverage             Run tests with coverage enabled.
    --with-profiling            Run tests with profiling enabled.
    --with-jit                  Run with JIT enabled.
    --with-mmap                 Run using mmap as binary loading method.
    --pass-testsuite-output     If set, output of testsuites will be passed
                                    directly to stdout/stderr.
    --hypothesis-profile        Set Hypothesis profile to PROFILE ("Default" by default)
    --clean-testsets            Remove testset dirs when building "clean" target.

  ${GREEN}Available variables:${CLR}
""")

ENV.Help(VARS.GenerateHelpText(ENV))

atexit.register(display_build_status)
