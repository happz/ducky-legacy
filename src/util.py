import colorama
import enum
import sys
import threading

from ctypes import sizeof
from console import VerbosityLevels

__all__ = ['debug', 'warn', 'error', 'info', 'quiet']

def debug(*args):
  global CONSOLE
  CONSOLE.writeln(VerbosityLevels.DEBUG, *args)

def info(*args):
  global CONSOLE
  CONSOLE.writeln(VerbosityLevels.INFO, *args)

def warn(*args):
  global CONSOLE
  CONSOLE.writeln(VerbosityLevels.WARNING, *args)

def error(*args):
  global CONSOLE
  CONSOLE.writeln(VerbosityLevels.ERROR, *args)

def quiet(*args):
  global CONSOLE
  CONSOLE.writeln(VerbosityLevels.QUIET, *args)

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
