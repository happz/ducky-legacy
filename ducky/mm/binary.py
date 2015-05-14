import enum
import mmap

from .. import cpu

from ..mm import UInt8, UInt32, ADDR_FMT
from ..util import debug, error, BinaryFile, StringTable, align
from ctypes import LittleEndianStructure, c_uint, c_ushort, c_ubyte, sizeof

class SectionTypes(enum.IntEnum):
  UNKNOWN = 0
  TEXT    = 1
  DATA    = 2
  SYMBOLS = 3
  STRINGS = 4

SECTION_TYPES = [
  'UNKNOWN', 'TEXT', 'DATA', 'SYMBOLS', 'STRINGS'
]

class SymbolDataTypes(enum.IntEnum):
  INT    = 0
  CHAR   = 1
  STRING = 2
  FUNCTION = 3
  ASCII  = 4
  BYTE   = 5

SYMBOL_DATA_TYPES = [
  'int', 'char', 'string', 'function', 'ascii', 'byte'
]

class FileFlags(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('mmapable', c_ushort, 1)
  ]

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',    c_ushort),
    ('version',  c_ushort),
    ('flags',    FileFlags),
    ('sections', c_ushort)
  ]

class SectionFlags(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('readable',   c_ubyte, 1),
    ('writable',   c_ubyte, 1),
    ('executable', c_ubyte, 1),
    ('bss',        c_ubyte, 1)
  ]

  @staticmethod
  def create(r, w, x, b):
    flags = SectionFlags()
    flags.readable = 1 if r else 0
    flags.writable = 1 if w else 0
    flags.executable = 1 if x else 0
    flags.bss = 1 if b else 0

    return flags

  def to_uint16(self):
    return self.readable | self.writable << 1 | self.executable << 2 | self.bss

  def from_uint16(self, u):
    self.readable = 1 if u & 0x01 else 0
    self.writable = 1 if u & 0x02 else 0
    self.executable = 1 if u & 0x04 else 0
    self.bss = 1 if u & 0x08 else 0

  def __repr__(self):
    return '<SectionFlags: r=%i, w=%i, x=%i, b=%i>' % (self.readable, self.writable, self.executable, self.bss)

class SectionHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index',   c_ubyte),
    ('name',    c_uint),
    ('type',    c_ubyte),
    ('flags',   SectionFlags),
    ('padding', c_ubyte),
    ('base',    c_ushort),
    ('items',   c_ushort),
    ('size',    c_ushort),
    ('offset',  c_uint)
  ]

  def __repr__(self):
    return '<SectionHeader: index=%i, name=%i, type=%i, flags=%s, base=%s, items=%s, size=%s, offset=%s>' % (self.index, self.name, self.type, self.flags, self.base, self.items, self.size, self.offset)

class SymbolEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('name',    c_uint),
    ('address', c_ushort),
    ('size',    c_ushort),
    ('section', c_ubyte),
    ('type',    c_ubyte),
    ('filename', c_uint),
    ('lineno',  c_uint)
  ]

  def __repr__(self):
    return '<SymbolEntry: section=%i, name=%s, type=%s, addr=%s>' % (self.section, self.name, SYMBOL_DATA_TYPES[self.type], ADDR_FMT(self.address))

SECTION_ITEM_SIZE = [
  0, 4, sizeof(UInt8), sizeof(SymbolEntry)
]

class File(BinaryFile):
  MAGIC = 0xDEAD
  VERSION = 1

  def __init__(self, *args, **kwargs):
    super(File, self).__init__(*args, **kwargs)

    self.__header = None
    self.__sections = []

    self.string_table = StringTable()

    self.symbols = None

  def create_header(self):
    self.__header = FileHeader()
    self.__header.magic = self.MAGIC
    self.__header.version = self.VERSION
    self.__header.sections = 0

    return self.__header

  def create_section(self):
    header = SectionHeader()
    header.index = len(self.__sections)
    self.__sections.append((header, []))
    return header

  def set_content(self, header, content):
    self.__sections[header.index] = (header, content)
    header.items = len(content)

  def get_header(self):
    return self.__header

  def get_section(self, i):
    return self.__sections[i]

  def load_symbols(self):
    self.symbols = {}

    for header, content in self.__sections:
      if header.type != SectionTypes.SYMBOLS:
        continue

      for symbol in content:
        self.symbols[self.string_table.get_string(symbol.name)] = symbol

  def load(self):
    self.seek(0)

    debug('load: loading headers')

    self.__header = self.read_struct(FileHeader)

    if self.__header.magic != self.MAGIC:
      error('load: magic cookie not recognized!')
      from ..mm import MalformedBinaryError
      raise MalformedBinaryError('Magic cookie not recognized!')

    for i in range(0, self.__header.sections):
      self.__sections.append((self.read_struct(SectionHeader), []))

    for i in range(0, self.__header.sections):
      header, content = self.__sections[i]

      debug('load: loading section #%i', header.index)

      self.seek(header.offset)

      if header.type == SectionTypes.STRINGS:
        self.string_table.buff = self.read(header.size)

      else:
        if header.type == SectionTypes.DATA:
          count = header.size
          st_class = UInt8

        elif header.type == SectionTypes.SYMBOLS:
          count = header.items
          st_class = SymbolEntry

        elif header.type == SectionTypes.TEXT:
          count = header.items
          st_class = UInt32

        else:
          from ..mm import MalformedBinaryError
          raise MalformedBinaryError('Unknown section header type %s' % header.type)

        for _ in range(0, count):
          content.append(self.read_struct(st_class))

  def save(self):
    self.seek(0)

    self.__header.sections = len(self.__sections)

    offset = sizeof(FileHeader) + sizeof(SectionHeader) * self.__header.sections

    if self.__header.flags.mmapable == 1:
      offset = align(mmap.PAGESIZE, offset)

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      header.offset = offset
      debug('set section %s offset to %s', self.string_table.get_string(header.name), offset)

      if header.type == SectionTypes.STRINGS:
        header.size = len(self.string_table.buff)

      if header.flags.bss != 1:
        offset += header.size
        debug('extending offset by %s to %s', header.size, offset)

        if self.__header.flags.mmapable == 1:
          offset = align(mmap.PAGESIZE, offset)
          debug('offset aligned to %s', offset)

      debug(str(header))
      debug('')

    debug('save: saving headers')

    self.write_struct(self.__header)

    for i in range(0, len(self.__sections)):
      self.write_struct(self.__sections[i][0])

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      debug('save: saving section %s: %s', self.string_table.get_string(header.name), header)

      self.seek(header.offset)

      if header.type == SectionTypes.STRINGS:
        debug('write: %s', self.string_table.buff)
        self.write(self.string_table.buff)

      elif header.flags.bss == 1:
        debug('BSS section - dont write out any slots')

      else:
        for item in content:
          if type(item) == cpu.assemble.SpaceSlot:
            debug('write_space: %s bytes', item.size.u16)
            self.write('\x00' * item.size.u16)

          else:
            self.write_struct(item)
