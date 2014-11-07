import ctypes
import enum
import struct

import cpu.instructions
import cpu.errors

from mm import UInt8, UInt16, UInt32
from util import debug, error
from ctypes import LittleEndianStructure, c_uint, c_ushort, c_ubyte, sizeof
from cpu.errors import CPUException

class SectionTypes(enum.IntEnum):
  UNKNOWN = 0
  TEXT    = 1
  DATA    = 2
  SYMBOLS = 3

SECTION_TYPES = [
  'UNKNOWN', 'TEXT', 'DATA', 'SYMBOLS'
]

class SymbolDataTypes(enum.IntEnum):
  INT    = 0
  CHAR   = 1
  STRING = 2
  FUNCTION = 3

SYMBOL_DATA_TYPES = [
  'int', 'char', 'string', 'function'
]

SECTION_NAME_LIMIT = 32
SYMBOL_NAME_LIMIT = 255

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

def ctypes_read_string(raw_string, max_len):
  s = ''

  for i in range(0, max_len):
    if raw_string[i] == 0:
      break

    s += chr(raw_string[i])

  return s

def ctypes_write_string(raw_string, max_len, s):
  # Avoid using undefined variable in case range does not start (len(name) == 0
  i = 0

  for i in range(0, min(len(s), max_len)):
    raw_string[i] = ord(s[i])

class SectionHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index',   c_ubyte),
    ('name',    c_ubyte * SECTION_NAME_LIMIT),
    ('type',    c_ubyte),
    ('flags',   SectionFlags),
    ('padding', c_ubyte),
    ('base',    c_ushort),
    ('size',    c_ushort),
    ('offset',  c_uint)
  ]

  def get_name(self):
    return ctypes_read_string(self.name, SECTION_NAME_LIMIT)

  def set_name(self, name):
    ctypes_write_string(self.name, SECTION_NAME_LIMIT, name)

class SymbolEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('name',    c_ubyte * (SYMBOL_NAME_LIMIT + 1)),
    ('address', c_ushort),
    ('size',    c_ushort),
    ('section', c_ubyte),
    ('type',    c_ubyte)
  ]

  def get_name(self):
    return ctypes_read_string(self.name, SECTION_NAME_LIMIT)

  def set_name(self, name):
    ctypes_write_string(self.name, SECTION_NAME_LIMIT, name)

SECTION_ITEM_SIZE = [
  0, sizeof(cpu.instructions.InstBinaryFormat_Master), sizeof(UInt8), 0, sizeof(SymbolEntry)
]

class File(file):
  MAGIC = 0xDEAD
  VERSION = 1

  def __init__(self, *args, **kwargs):
    if args[1] == 'w':
      args = (args[0], 'wb')

    elif args[1] == 'r':
      args = (args[0], 'rb')

    super(File, self).__init__(*args, **kwargs)

    self.__header = None
    self.__sections = []

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
    header.size = len(content)

  def get_header(self):
    return self.__header

  def get_section(self, i):
    return self.__sections[i]

  def read_struct(self, st_class):
    debug('read_struct: class=%s (%s bytes)' % (st_class, sizeof(st_class)))

    st = st_class()
    self.readinto(st)
    return st

  def write_struct(self, st):
    debug('write_struct: class=%s (%s bytes)' % (st.__class__, sizeof(st)))

    self.write(st)

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

      debug('load: loading section #%i' % header.index)

      self.seek(header.offset)

      i = 0
      while i < header.size:
        if header.type == SectionTypes.DATA:
          st_class = UInt8

        elif header.type == SectionTypes.SYMBOLS:
          st_class = SymbolEntry

        elif header.type == SectionTypes.TEXT:
          st_class = cpu.instructions.InstBinaryFormat_Master

        else:
          raise cpu.error.MalformedBinaryError('Unknown section header type %s' % header.type)

        content.append(self.read_struct(st_class))
        i += 1

  def save(self):
    self.seek(0)

    self.__header.sections = len(self.__sections)

    offset = sizeof(FileHeader) + sizeof(SectionHeader) * self.__header.sections

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      debug('section %s, size %s, offset %s' % (header.get_name(), header.size, offset))
      header.size = len(content)
      header.offset = offset

      offset += header.size * SECTION_ITEM_SIZE[header.type]

    debug('save: saving headers')

    self.write_struct(self.__header)

    for i in range(0, len(self.__sections)):
      self.write_struct(self.__sections[i][0])

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      debug('save: saving section #%i' % header.index)

      self.seek(header.offset)

      for j in range(0, len(content)):
        self.write_struct(content[j])

