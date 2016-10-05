import collections
import functools
import string

from six import iteritems, integer_types, PY2

from ctypes import sizeof

def align(boundary, n):
  return (n + boundary - 1) & ~(boundary - 1)

def str2int(s):
  if isinstance(s, integer_types):
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
  def format_field(self, value, format_spec):
    if format_spec and format_spec[-1] in 'BSWL':
      return self.format_int(format_spec, value)

    return super(Formatter, self).format_field(value, format_spec)

  def format_int(self, format_spec, value):
    i = value if isinstance(value, integer_types) else value.value

    if format_spec.endswith('B'):
      return '0x{:02X}'.format(i & 0xFF)

    if format_spec.endswith('S'):
      return '0x{:04X}'.format(i & 0xFFFF)

    if format_spec.endswith('W'):
      return '0x{:08X}'.format(i & 0xFFFFFFFF)

    if format_spec.endswith('L'):
      return '0x{:016X}'.format(i & 0xFFFFFFFFFFFFFFFF)

    return '{:d}'.format(i)

_F = Formatter()
F = _F.format

UINT8_FMT  = functools.partial(_F.format_int, 'B')
UINT16_FMT = functools.partial(_F.format_int, 'S')
UINT32_FMT = functools.partial(_F.format_int, 'W')
UINT64_FMT = functools.partial(_F.format_int, 'L')


if PY2:
  _BaseFile = file  # noqa

  bytes2str = str
  str2bytes = str
  int2bytes = chr

else:
  from io import IOBase as _BaseFile
  import functools

  bytes2str = functools.partial(str, encoding = 'latin-1')
  str2bytes = functools.partial(bytes, encoding = 'latin-1')

  def int2bytes(b):
    return bytes([b])

def isfile(o):
  return isinstance(o, (_BaseFile, BinaryFile))


class BinaryFile(object):
  """
  Base class of all classes that represent "binary" files - binaries, core dumps.
  It provides basic methods for reading and writing structures.
  """

  @staticmethod
  def do_open(logger, path, mode = 'rb', klass = None):
    if 'b' not in mode:
      mode += 'b'

    stream = open(path, mode)

    if not PY2:
      import io

      if 'r' in mode:
        if 'w' in mode:
          stream = io.BufferedRandom(stream)

        else:
          stream = io.BufferedReader(stream)

      else:
        stream = io.BufferedWriter(stream)

    klass = klass or BinaryFile

    return klass(logger, stream)

  @staticmethod
  def open(*args, **kwargs):
    return BinaryFile.do_open(*args, **kwargs)

  def __init__(self, logger, stream):
    self.stream = stream

    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warning
    self.ERROR = logger.error
    self.EXCEPTION = logger.exception

    self.close = stream.close
    self.flush = stream.flush
    self.name = stream.name
    self.read = stream.read
    self.readinto = stream.readinto
    self.readline = stream.readline
    self.seek = stream.seek
    self.tell = stream.tell
    self.write = stream.write

    self.mode = stream.mode

    self.setup()

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    self.close()

  def setup(self):
    pass

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

class StringTable(object):
  """
  Simple string table, used by many classes operating with files (core, binaries, ...).
  String can be inserted into table and read, each has its starting offset and its end is
  marked with null byte (\0).

  Thsi is a helper class - it makes working with string, e.g. section and symbol names,
  much easier.
  """

  def __init__(self, buff = None):
    super(StringTable, self).__init__()

    self.buff = buff if buff is not None else ''

  @property
  def buff(self):
    """
    Serialize internal string table to a stream of bytes.
    """

    if self._buff is not None:
      return self._buff

    self._buff = ''

    for s, (l, offset) in iteritems(self._string_to_offset):
      self._buff += l
      self._buff += s

    return self._buff

  @buff.setter
  def buff(self, buff):
    self._string_to_offset = collections.OrderedDict()
    self._offset_to_string = {}

    buff_len = len(buff)
    offset = 0

    while offset < buff_len:
      l = ord(buff[offset])
      s = buff[offset + 1:offset + 1 + l]

      self._string_to_offset[s] = (chr(l), offset)
      self._offset_to_string[offset] = s

      offset += 1 + l

    self._buff = buff
    self._offset = offset

  def put_string(self, s):
    """
    Insert new string into table. String is appended at the end of internal buffer.

    :returns: offset of inserted string
    :rtype: ``int``
    """

    if s not in self._string_to_offset:
      l = len(s)

      self._string_to_offset[s] = (chr(l), self._offset)
      self._offset_to_string[self._offset] = s

      self._offset += 1 + l

      self._buff = None

    return self._string_to_offset[s][1]

  def get_string(self, offset):
    """
    Read string from table.

    :param int offset: offset of the first character from the beginning of the table
    :returns: string
    :rtype: ``string``
    """

    return self._offset_to_string[offset]

class SymbolTable(dict):
  def __init__(self, binary):
    self.binary = binary

  def __getitem__(self, address):
    last_symbol = None
    last_symbol_offset = 0xFFFE

    for symbol_name, symbol in iteritems(self.binary.symbols):
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


class Flags(object):
  _flags = []
  _labels = ''
  _encoding = []  # silence Codacy warning - _encoding will have a real value

  @classmethod
  def create(cls, **kwargs):
    flags = cls()

    for name in cls._flags:
      setattr(flags, name, True if kwargs.get(name, False) is True else False)

    return flags

  @classmethod
  def encoding(cls):
    return cls._encoding

  @classmethod
  def from_encoding(cls, encoding):
    flags = cls()
    flags.load_encoding(encoding)
    return flags

  def to_encoding(self):
    encoding = self._encoding()
    self.save_encoding(encoding)
    return encoding

  def load_encoding(self, encoding):
    for name in [field[0] for field in encoding._fields_]:
      setattr(self, name, True if getattr(encoding, name) == 1 else False)

  def save_encoding(self, encoding):
    for name in [field[0] for field in encoding._fields_]:
      setattr(encoding, name, 1 if getattr(self, name) is True else 0)

  def to_int(self):
    u = 0

    for i, name in enumerate(self._flags):
      if getattr(self, name) is True:
        u |= (1 << i)

    return u

  def load_int(self, u):
    for i, name in enumerate(self._flags):
      setattr(self, name, True if u & (1 << i) else False)

  @classmethod
  def from_int(cls, u):
    flags = cls()
    flags.load_int(u)
    return flags

  def to_string(self):
    return ''.join([
      self._labels[i] if getattr(self, name) is True else '-' for i, name in enumerate(self._flags)
    ])

  def load_string(self, s):
    s = s.upper()

    for i, name in enumerate(self._flags):
      setattr(self, name, True if self._labels[i] in s else False)

  @classmethod
  def from_string(cls, s):
    flags = cls()
    flags.load_string(s)
    return flags

  def __repr__(self):
    return '<{}: {}>'.format(self.__class__.__name__, self.to_string())

class LoggingCapable(object):
  def __init__(self, logger, *args, **kwargs):
    super(LoggingCapable, self).__init__(*args, **kwargs)

    self._logger = logger

    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warn
    self.ERROR = logger.error
    self.EXCEPTION = logger.exception
