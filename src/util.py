import collections
import colorama
import enum
import functools
import sys
import tabulate
import traceback
import types

from ctypes import sizeof
from console import VerbosityLevels

__all__ = ['debug', 'warn', 'error', 'info', 'quiet', 'exception']

def align(boundary, n):
  return (n + boundary - 1) & ~(boundary - 1)

def str2int(s):
  if type(s) == types.IntType:
    return s

  if s.startswith('0x'):
    return int(s, base = 16)

  if s.startswith('0'):
    return int(s, base = 8)

  return int(s)

def __log(level, *args):
  global CONSOLE
  CONSOLE.writeln(level, *args)

debug = functools.partial(__log, VerbosityLevels.DEBUG)
info  = functools.partial(__log, VerbosityLevels.INFO)
warn  = functools.partial(__log, VerbosityLevels.WARNING)
error = functools.partial(__log, VerbosityLevels.ERROR)
quiet = functools.partial(__log, VerbosityLevels.QUIET)

def exception(exc, logger = None):
  logger = logger or error

  logger(str(exc))
  logger('')

  if hasattr(exc, 'exc_stack'):
    for line in traceback.format_exception(*exc.exc_stack):
      line = line.rstrip()

      for line in line.split('\n'):
        line = line.replace('%', '%%')
        logger(line)

    logger('')

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

class LRUCache(collections.OrderedDict):
  def __init__(self, size, *args, **kwargs):
    super(LRUCache, self).__init__(*args, **kwargs)

    self.size = size

    self.reads   = 0
    self.inserts = 0
    self.hits    = 0
    self.misses  = 0
    self.prunes  = 0

  def make_space(self):
    self.popitem(last = False)
    self.prunes += 1

  def __getitem__(self, key):
    debug('LRUCache: get: key=%s', key)

    self.reads += 1

    if key in self:
      self.hits += 1
    else:
      self.misses += 1

    return super(LRUCache, self).__getitem__(key)

  def __setitem__(self, key, value):
    debug('LRUCache: set: key=%s, value=%s', key, value)

    if len(self) == self.size:
      self.make_space()

    super(LRUCache, self).__setitem__(key, value)
    self.inserts += 1

  def get_object(self, key):
    return None

  def __missing__(self, key):
    debug('LRUCache: missing: key=%s', key)

    self[key] = value = self.get_object(key)
    return value

class StringTable(object):
  def __init__(self):
    super(StringTable, self).__init__()

    self.buff = ''

  def put_string(self, s):
    offset = len(self.buff)

    #debug('put_string: s=%s, offset=%s', s, offset)

    self.buff += s + '\x00'

    return offset

  def get_string(self, offset):
    #debug('get_string: offset=%s', offset)

    s = ''

    for i in range(offset, len(self.buff)):
      c = self.buff[i]

      if c == '\x00':
        break

      s += c

    #debug('  string="%s"', s)

    return s
