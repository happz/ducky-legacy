import ctypes
import enum
import struct

import cpu.instructions
import cpu.errors

from mm import UInt8, UInt16, UInt32
from util import debug, error, BinaryFile
from ctypes import LittleEndianStructure, c_uint, c_ushort, c_ubyte, sizeof
from cpu.errors import CPUException

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

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',   c_ushort),
    ('version', c_ushort),
    ('sections', c_ushort),
  ]

class SectionFlags(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('readable',   c_ubyte, 1),
    ('writable',   c_ubyte, 1),
    ('executable', c_ubyte, 1),
    ('bss',        c_ubyte, 1)
  ]

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
    ('type',    c_ubyte)
  ]

  def __repr__(self):
    return '<SymbolEntry: section=%i, name=%s, type=%s>' % (self.section, self.name, SYMBOL_DATA_TYPES[self.type])

SECTION_ITEM_SIZE = [
  0, sizeof(cpu.instructions.InstBinaryFormat_Master), sizeof(UInt8), sizeof(SymbolEntry)
]

class StringTable(object):
  def __init__(self):
    super(StringTable, self).__init__()

    self.buff = ''

  def put_string(self, s):
    offset = len(self.buff)

    debug('put_string: s=%s, offset=%s', s, offset)

    self.buff += s + '\x00'

    return offset

  def get_string(self, offset):
    debug('get_string: offset=%s', offset)

    s = ''

    for i in range(offset, len(self.buff)):
      c = self.buff[i]
      if c == '\x00':
        break
      s += c

    debug('  string="%s"', s)

    return s

class File(BinaryFile):
  MAGIC = 0xDEAD
  VERSION = 1

  def __init__(self, *args, **kwargs):
    super(File, self).__init__(*args, **kwargs)

    self.__header = None
    self.__sections = []

    self.string_table = StringTable()

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

  def load(self):
    self.seek(0)

    debug('load: loading headers')

    self.__header = self.read_struct(FileHeader)

    if self.__header.magic != self.MAGIC:
      error('load: magic cookie not recognized!')
      raise cpu.errors.MalformedBinaryError('Magic cookie not recognized!')

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
          st_class = UInt8

        elif header.type == SectionTypes.SYMBOLS:
          st_class = SymbolEntry

        elif header.type == SectionTypes.TEXT:
          st_class = cpu.instructions.InstBinaryFormat_Master

        else:
          raise cpu.error.MalformedBinaryError('Unknown section header type %s' % header.type)

        for _ in range(0, header.items):
          content.append(self.read_struct(st_class))

  def save(self):
    self.seek(0)

    self.__header.sections = len(self.__sections)

    offset = sizeof(FileHeader) + sizeof(SectionHeader) * self.__header.sections

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      header.offset = offset

      if header.type == SectionTypes.STRINGS:
        header.size = len(self.string_table.buff)

      else:
        header.items = len(content)
        header.size = header.items * SECTION_ITEM_SIZE[header.type]

      debug('save: %s', header)

      offset += header.size

    debug('save: saving headers')

    self.write_struct(self.__header)

    for i in range(0, len(self.__sections)):
      self.write_struct(self.__sections[i][0])

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      debug('save: saving section %s', header)

      self.seek(header.offset)

      if header.type == SectionTypes.STRINGS:
        debug('write: %s', self.string_table.buff)
        self.write(self.string_table.buff)

      else:
        for item in content:
          self.write_struct(item)
