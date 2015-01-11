import colorama
import enum
import functools
import sys
import threading
import tabulate
import types

from ctypes import sizeof
from console import VerbosityLevels

__all__ = ['debug', 'warn', 'error', 'info', 'quiet']

def str2int(s):
  if type(s) == types.IntType:
    return s

  if s.startswith('0x'):
    return int(s, base = 16)

  if s.startswith('0'):
    return int(s, base = 8)

  return int(s)

def __active_log(verbosity_level, *args):
  global CONSOLE
  CONSOLE.writeln(verbosity_level, *args)

__active_debug = functools.partial(__active_log, VerbosityLevels.DEBUG)
__active_info  = functools.partial(__active_log, VerbosityLevels.INFO)
__active_warn  = functools.partial(__active_log, VerbosityLevels.WARNING)
__active_error = functools.partial(__active_log, VerbosityLevels.ERROR)
__active_quiet = functools.partial(__active_log, VerbosityLevels.QUIET)

def __inactive_log(*args):
  pass

debug = __active_debug
info  = __active_info
warn  = __active_warn
error = __active_error
quiet = __active_quiet

def print_table(table, fn = info, **kwargs):
  for line in tabulate.tabulate(table, headers = 'firstrow', tablefmt = 'simple', numalign = 'right').split('\n'):
    fn(line)

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

    debug('read_struct: %s: %s bytes: %s', pos, sizeof(st_class), st)

    return st

  def write_struct(self, st):
    pos = self.tell()

    debug('write_struct: %s: %s bytes: %s', pos, sizeof(st), st)

    self.write(st)
