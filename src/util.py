import colorama
import enum
import sys
import threading

from ctypes import sizeof

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

  VERBOSITY = level + 1

STDOUT_LOCK = threading.Lock()

def log(lvl, *args):
  if lvl > VERBOSITY:
    return

  with STDOUT_LOCK:
    print COLORS[lvl],
    print '[%s]' % LEVELS[lvl],
    for arg in args:
      print arg,

    print colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL,
    print

    sys.stdout.flush()

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

class BinaryFile(file):
  def __init__(self, *args, **kwargs):
    if args[1] == 'w':
      args = (args[0], 'wb')

    elif args[1] == 'r':
      args = (args[0], 'rb')

    super(BinaryFile, self).__init__(*args, **kwargs)

  def read_struct(self, st_class):
    pos = self.tell()

    st = st_class()
    self.readinto(st)

    debug('read_struct: %s: %s bytes: %s' % (pos, sizeof(st_class), st))

    return st

  def write_struct(self, st):
    pos = self.tell()

    debug('write_struct: %s: %s bytes: %s' % (pos, sizeof(st), st))

    self.write(st)
