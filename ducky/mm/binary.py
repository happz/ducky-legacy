import enum
import mmap

from six.moves import range

from .. import cpu

from ..mm import UInt8, UInt32, ADDR_FMT
from ..util import BinaryFile, StringTable, align, Flags, str2bytes, bytes2str
from ctypes import LittleEndianStructure, c_uint, c_ushort, c_ubyte, sizeof

class SectionFlags(Flags):
  _fields_ = [
    ('readable',   c_ubyte, 1),
    ('writable',   c_ubyte, 1),
    ('executable', c_ubyte, 1),
    ('loadable',   c_ubyte, 1),
    ('bss',        c_ubyte, 1),
    ('mmapable',   c_ubyte, 1),
    ('globally_visible', c_ubyte, 1),
  ]

  flag_labels = 'RWELBMG'

class SectionTypes(enum.IntEnum):
  UNKNOWN = 0
  TEXT    = 1
  DATA    = 2
  SYMBOLS = 3
  STRINGS = 4
  RELOC   = 5

SECTION_TYPES = [
  'UNKNOWN', 'TEXT', 'DATA', 'SYMBOLS', 'STRINGS', 'RELOC'
]

class SymbolDataTypes(enum.IntEnum):
  INT    = 0
  CHAR   = 1
  STRING = 2
  FUNCTION = 3
  ASCII  = 4
  BYTE   = 5
  UNKNOWN = 6

SYMBOL_DATA_TYPES = 'ICSFABU'

class FileFlags(Flags):
  _fields_ = [
    ('mmapable', c_ushort, 1)
  ]

  flag_labels = 'M'

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',    c_ushort),
    ('version',  c_ushort),
    ('flags',    FileFlags),
    ('sections', c_ushort)
  ]

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
    ('data_size', c_ushort),
    ('file_size', c_ushort),
    ('offset',  c_uint)
  ]

  def __repr__(self):
    return '<SectionHeader: index={}, name={}, type={}, flags={}, base={}, items={}, data_size={}, file_size={}, offset={}>'.format(self.index, self.name, self.type, self.flags.to_string(), ADDR_FMT(self.base), self.items, self.data_size, self.file_size, self.offset)

class SymbolFlags(Flags):
  _fields_ = [
    ('globally_visible', c_ushort, 1)
  ]

  flag_labels = 'G'

class SymbolEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('flags',        SymbolFlags),
    ('name',         c_uint),
    ('address',      c_ushort),
    ('size',         c_ushort),
    ('section',      c_ubyte),
    ('type',         c_ubyte),
    ('filename',     c_uint),
    ('lineno',       c_uint)
  ]

  def __repr__(self):
    return '<SymbolEntry: section={}, name={}, type={}, addr={}, flags={}>'.format(self.section, self.name, SYMBOL_DATA_TYPES[self.type], ADDR_FMT(self.address), self.flags.to_string())

class RelocFlags(Flags):
  _fields_ = [
    ('relative', c_ushort, 1)
  ]

  flag_labels = 'R'

class RelocEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('flags',         RelocFlags),
    ('name',          c_uint),
    ('patch_section', c_ubyte),
    ('patch_address', c_ushort),
    ('patch_offset',  c_ubyte),
    ('patch_size',    c_ubyte),
  ]

  def __repr__(self):
    return '<RelocEntry: flags=%s, name=%s, section=%s, address=%s, offset=%s, size=%s>' % (self.flags.to_string(), self.name, self.patch_section, ADDR_FMT(self.patch_address), self.patch_offset, self.patch_size)

SECTION_ITEM_SIZE = [
  0, 4, sizeof(UInt8), sizeof(SymbolEntry)
]

class File(BinaryFile):
  MAGIC = 0xDEAD
  VERSION = 1

  @staticmethod
  def open(*args, **kwargs):
    return BinaryFile.do_open(*args, klass = File, **kwargs)

  def setup(self):
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

  def sections(self):
    return (self.get_section(i) for i in range(0, self.get_header().sections))

  def get_section(self, i):
    return self.__sections[i]

  def get_section_by_name(self, name):
    for i in range(0, self.get_header().sections):
      header, content = self.get_section(i)

      if self.string_table.get_string(header.name) == name:
        return header, content

    from ..mm import MalformedBinaryError
    raise MalformedBinaryError('Unknown section named "{}"'.format(name))

  def load_symbols(self):
    self.symbols = {}

    for header, content in self.__sections:
      if header.type != SectionTypes.SYMBOLS:
        continue

      for symbol in content:
        self.symbols[self.string_table.get_string(symbol.name)] = symbol

  def load(self):
    self.seek(0)

    self.DEBUG('load: loading headers')

    self.__header = self.read_struct(FileHeader)

    if self.__header.magic != self.MAGIC:
      self.ERROR('load: magic cookie not recognized!')
      from ..mm import MalformedBinaryError
      raise MalformedBinaryError('Magic cookie not recognized!')

    for i in range(0, self.__header.sections):
      self.__sections.append((self.read_struct(SectionHeader), []))

    for i in range(0, self.__header.sections):
      header, content = self.__sections[i]

      self.DEBUG('load: loading section #%i', header.index)

      self.seek(header.offset)

      if header.type == SectionTypes.STRINGS:
        self.string_table.buff = bytes2str(self.read(header.file_size))

      else:
        if header.type == SectionTypes.DATA:
          count = header.data_size
          st_class = UInt8

        elif header.type == SectionTypes.SYMBOLS:
          count = header.items
          st_class = SymbolEntry

        elif header.type == SectionTypes.TEXT:
          count = header.items
          st_class = UInt32

        elif header.type == SectionTypes.RELOC:
          count = header.items
          st_class = RelocEntry

        else:
          from ..mm import MalformedBinaryError
          raise MalformedBinaryError('Unknown section header type {}'.format(header.type))

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
      self.DEBUG('set section %s offset to %s', self.string_table.get_string(header.name), offset)

      if header.type == SectionTypes.STRINGS:
        header.data_size = header.file_size = len(self.string_table.buff)

      if header.flags.bss != 1:
        offset += header.file_size
        self.DEBUG('extending offset by %s to %s', header.file_size, offset)

        if self.__header.flags.mmapable == 1:
          offset = align(mmap.PAGESIZE, offset)
          self.DEBUG('offset aligned to %s', offset)

      self.DEBUG(str(header))
      self.DEBUG('')

    self.DEBUG('save: saving headers')

    self.write_struct(self.__header)

    for i in range(0, len(self.__sections)):
      self.write_struct(self.__sections[i][0])

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      self.DEBUG('save: saving section %s: %s', self.string_table.get_string(header.name), header)

      self.seek(header.offset)

      if header.type == SectionTypes.STRINGS:
        self.DEBUG('write: %s', self.string_table.buff)
        self.write(str2bytes(self.string_table.buff))

      elif header.flags.bss == 1:
        self.DEBUG('BSS section - dont write out any slots')

      else:
        for item in content:
          if type(item) == cpu.assemble.SpaceSlot:
            self.DEBUG('write_space: %s bytes', item.size.u16)
            self.write(str2bytes('\x00' * item.size.u16))

          else:
            self.write_struct(item)

        if header.data_size != header.file_size:
          self.DEBUG('write after-section padding of %s bytes', header.file_size - header.data_size)
          self.write(str2bytes('\x00' * (header.file_size - header.data_size)))
