import colorama
import enum

__all__ = ['debug', 'warn', 'error', 'info', 'quiet']

class VerbosityLevels(enum.IntEnum):
  QUIET   = 0
  ERROR   = 1
  WARNING = 2
  INFO    = 3
  DEBUG   = 4

LEVELS = [
  '',
  'ERRR',
  'WARN',
  'INFO',
  'DEBG'
]

COLORS = [
  None,
  colorama.Fore.RED,
  colorama.Fore.YELLOW,
  colorama.Fore.GREEN,
  colorama.Fore.WHITE
]

VERBOSITY = VerbosityLevels.ERROR

def set_verbosity(level):
  global VERBOSITY

  VERBOSITY = level

def log(lvl, *args):
  if lvl > VERBOSITY:
    return

  print COLORS[lvl],
  print '[%s]' % LEVELS[lvl],
  for arg in args:
    print arg,

  print colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL,
  print

def debug(*args):
  log(VerbosityLevels.DEBUG, *args)

def info(*args):
  log(VerbosityLevels.INFO, *args)

def warn(*args):
  log(VerbosityLevels.WARNING, *args)

def error(*args):
  log(VerbosityLevels.ERROR, *args)

def quiet(*args):
  log(VerbosityLevels.QUIET, *args)

