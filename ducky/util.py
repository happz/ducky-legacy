import collections
import functools
import string
import types

from ctypes import sizeof, LittleEndianStructure

def align(boundary, n):
  return (n + boundary - 1) & ~(boundary - 1)

def str2int(s):
  if isinstance(s, types.IntType):
    return s

  if s.startswith('0x'):
    return int(s, base = 16)

  if s.startswith('0'):
    return int(s, base = 8)

  return int(s)

def sizeof_fmt(n, suffix = 'B', max_unit = 'Zi'):
  for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
    if abs(n) < 1024.0 or max_unit == unit:
      return "%3.1f%s%s" % (n, unit, suffix)

    n /= 1024.0

  return "%.1f%s%s" % (n, 'Yi', suffix)

class Formatter(string.Formatter):
  @staticmethod
  def uint_to_int(u):
    from .mm import UInt8, UInt16, UInt24, UInt32

    if type(u) == UInt8:
     return u.u8

    if type(u) == UInt16:
      return u.u16

    if type(u) == UInt24:
      return u.u24

    if type(u) == UInt32:
      return u.u32

    return u

  def format_field(self, value, format_spec):
    if format_spec and format_spec[-1] in 'BWAL':
      return self.format_int(format_spec, value)

    return super(Formatter, self).format_field(value, format_spec)

  def format_int(self, format_spec, value):
    if format_spec.endswith('B'):
      return '0x{:02X}'.format(Formatter.uint_to_int(value) & 0xFF)

    if format_spec.endswith('W'):
      return '0x{:04X}'.format(Formatter.uint_to_int(value) & 0xFFFF)

    if format_spec.endswith('A'):
      return '0x{:06X}'.format(Formatter.uint_to_int(value) & 0xFFFFFF)

    if format_spec.endswith('L'):
      return '0x{:08X}'.format(Formatter.uint_to_int(value))

    return '{:d}'.format(value)

_F = Formatter()
F = _F.format

UINT_FMT   = Formatter.uint_to_int
UINT8_FMT  = functools.partial(_F.format_int, 'B')
UINT16_FMT = functools.partial(_F.format_int, 'W')
UINT24_FMT = functools.partial(_F.format_int, 'A')
UINT32_FMT = functools.partial(_F.format_int, 'L')
ADDR_FMT   = functools.partial(_F.format_int, 'A')


import __builtin__
if not hasattr(__builtin__, 'orig_file'):
  __builtin__.orig_file = None
  __builtin__.orig_open = None

def isfile(o):
  if isinstance(o, file):
    return True

  return hasattr(__builtin__, 'orig_file') and __builtin__.orig_file is not None and isinstance(o, __builtin__.orig_file)

class FileOpenPatcher(object):
  def __init__(self, logger):
    self.logger = logger

    self.old_file = None
    self.old_open = None
    self.open_files = None

  def patch(self):
    logger = self.logger

    self.open_files = open_files = set()

    self.old_file = old_file = __builtin__.orig_file = __builtin__.file
    self.old_open = __builtin__.orig_open = __builtin__.open

    class NewFile(old_file):
      def __init__(self, *args):
        old_file.__init__(self, *args)

        open_files.add(self)
        logger.debug('Opening file: %s', args[0])

      def close(self):
        try:
          old_file.close(self)
        except IOError:
          logger.exception('Exception raised when closing a file: %s', self)

        open_files.remove(self)
        logger.debug('Closing file: %s', self)

    def new_open(*args):
      return NewFile(*args)

    __builtin__.file = NewFile
    __builtin__.open = new_open

  def restore(self):
    __builtin__.file = self.old_file
    __builtin__.open = self.old_open

    __builtin__.orig_file = None
    __builtin__.orig_open = None

  def has_open_files(self):
    return len(self.open_files) > 0

  def log_open_files(self):
    self.logger.warn('Opened files: %i files were not closed', len(self.open_files))

    for f in self.open_files:
      self.logger.warn('  %s', repr(f))

class BinaryFile(file):
  """
  Base class of all classes that represent "binary" files - binaries, core dumps.
  It provides basic methods for reading and writing structures.
  """

  open_files = set()

  def __init__(self, logger, *args, **kwargs):
    if args[1] == 'w':
      args = (args[0], 'wb')

    elif args[1] == 'r':
      args = (args[0], 'rb')

    super(BinaryFile, self).__init__(*args, **kwargs)

    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warning
    self.ERROR = logger.error
    self.EXCEPTION = logger.exception

    self.DEBUG('Opening file: %s', args[0])
    BinaryFile.open_files.add(self)

  def close(self):
    try:
      super(BinaryFile, self).close()
    except IOError:
      self.EXCEPTION('Exception raised when closing a file: %s', self)

    self.DEBUG('Closing file: %s', repr(self))
    BinaryFile.open_files.remove(self)

  def read_struct(self, st_class):
    """
    Read structure from current position in file.

    :returns: instance of class ``st_class`` with content read from file
    :rtype: ``st_class``
    """

    pos = self.tell()

    st = st_class()
    self.readinto(st)

    self.DEBUG('read_struct: %s: %s bytes: %s', pos, sizeof(st_class), st)

    return st

  def write_struct(self, st):
    """
    Write structure into file at the current position.

    :param class st: ``ctype``-based structure
    """

    pos = self.tell()

    self.DEBUG('write_struct: %s: %s bytes: %s', pos, sizeof(st), st)

    self.write(st)

class LRUCache(collections.OrderedDict):
  """
  Simple LRU cache, based on ``OrderedDict``, with limited size. When limit
  is reached, the least recently inserted item is removed.

  :param logging.Logger logger: logger object instance should use for logging.
  :param int size: maximal number of entries allowed.
  """

  def __init__(self, logger, size, *args, **kwargs):
    super(LRUCache, self).__init__(*args, **kwargs)

    self.size = size

    self.reads   = 0
    self.inserts = 0
    self.hits    = 0
    self.misses  = 0
    self.prunes  = 0

    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warn
    self.ERROR = logger.error
    self.EXCEPTION = logger.exception

  def make_space(self):
    """
    This method is called when there is no free space in cache. It's responsible
    for freeing at least one slot, upper limit of removed entries is not enforced.
    """

    self.DEBUG('%s.make_space', self.__class__.__name__)

    self.popitem(last = False)
    self.prunes += 1

  def __getitem__(self, key):
    """
    Return entry with specified key.
    """

    self.DEBUG('%s.__getitem__: key=%s', self.__class__.__name__, key)

    self.reads += 1

    if key in self:
      self.hits += 1
    else:
      self.misses += 1

    return super(LRUCache, self).__getitem__(key)

  def __setitem__(self, key, value):
    """
    Called when item is inserted into cache. Size limit is checked and if there's no free
    space in cache, ``make_space`` method is called.
    """

    self.DEBUG('%s.__setitem__: key=%s, value=%s', self.__class__.__name__, key, value)

    if len(self) == self.size:
      self.make_space()

    super(LRUCache, self).__setitem__(key, value)
    self.inserts += 1

  def get_object(self, key):
    """
    The real workhorse - responsible for getting requested item from outside when it's
    not present in cache. Called by ``__missing__`` method. This method itself makes no
    changes to cache at all.
    """

    raise NotImplementedError('Cache %s does not implement get() method' % self.__class__.__name__)

  def __missing__(self, key):
    """
    Called when requested entry is not in cache. It's responsible for getting missing item
    and inserting it into cache. Returns new item.
    """

    self.DEBUG('%s.__missing__: key=%s', self.__class__.__name__, key)

    self[key] = value = self.get_object(key)
    return value

class StringTable(object):
  """
  Simple string table, used by many classes operating with files (core, binaries, ...).
  String can be inserted into table and read, each has its starting offset and its end is
  marked with null byte (\0).

  Thsi is a helper class - it makes working with string, e.g. section and symbol names,
  much easier.
  """

  def __init__(self):
    super(StringTable, self).__init__()

    self.buff = ''

  def put_string(self, s):
    """
    Insert new string into table. String is appended at the end of internal buffer,
    and terminating zero byte (\0) is appended to mark end of string.

    :returns: offset of inserted string
    :rtype: ``int``
    """

    offset = len(self.buff)

    self.buff += s + '\x00'

    return offset

  def get_string(self, offset):
    """
    Read string from table.

    :param int offset: offset of the first character from the beginning of the table
    :returns: string
    :rtype: ``string``
    """

    s = []

    for i in xrange(offset, len(self.buff)):
      c = self.buff[i]

      if c == '\x00':
        break

      s.append(c)

    return ''.join(s)

class SymbolTable(dict):
  def __init__(self, binary):
    self.binary = binary

  def __getitem__(self, address):
    last_symbol = None
    last_symbol_offset = 0xFFFE

    for symbol_name, symbol in self.binary.symbols.iteritems():
      if symbol.address > address:
        continue

      if symbol.address == address:
        return (symbol_name, 0)

      offset = abs(address - symbol.address)
      if offset < last_symbol_offset:
        last_symbol = symbol_name
        last_symbol_offset = offset

    return (last_symbol, last_symbol_offset)

  def get_symbol(self, name):
    return self.binary.symbols[name]

class Flags(LittleEndianStructure):
  _pack_ = 0
  flag_labels = []

  @classmethod
  def create(cls, **kwargs):
    flags = cls()

    for name, _type, _size in cls._fields_:
      setattr(flags, name, 1 if kwargs.get(name, False) is True else 0)

    return flags

  def to_uint16(self):
    u = 0

    for i, (name, _type, _size) in enumerate(self._fields_):
      u |= (getattr(self, name) << i)

    return u

  def load_uint16(self, u):
    for i, (name, _type, _size) in enumerate(self._fields_):
      setattr(self, name, 1 if u & (1 << i) else 0)

  @classmethod
  def from_uint16(cls, u):
    flags = cls()
    flags.load_uint16(u)
    return flags

  def to_string(self):
    return ''.join([
      self.flag_labels[i] if getattr(self, name) == 1 else '-' for i, (name, _type, _size) in enumerate(self._fields_)
    ])

  def load_string(self, s):
    s = s.upper()

    for i, (name, _type, _size) in enumerate(self._fields_):
      setattr(self, name, 1 if self.flag_labels[i] in s else 0)

  @classmethod
  def from_string(cls, s):
    flags = cls()
    flags.load_string(s)
    return flags

  def __repr__(self):
    return '<{}: {}>'.format(self.__class__.__name__, self.to_string())
