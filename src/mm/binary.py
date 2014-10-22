import enum
import struct

import cpu.instructions
import cpu.errors

from mm import UInt8, UInt16, UInt32
from util import *
from ctypes import LittleEndianStructure, c_uint, c_ushort, c_ubyte, sizeof

class SectionTypes(enum.IntEnum):
  TEXT    = 0
  DATA    = 1
  STACK   = 2
  SYMBOLS = 3

SECTION_TYPES = [
  'TEXT', 'DATA', 'STACK', 'SYMBOLS'
]

SYMBOL_NAME_LIMIT = 255

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',   c_ushort),
    ('version', c_ushort),
    ('sections', c_ushort),
  ]

class SectionHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index', c_ubyte),
    ('type',  c_ubyte),
    ('flags', c_ubyte),
    ('padding', c_ubyte),
    ('base',  c_ushort),
    ('size',  c_ushort),
    ('offset', c_uint)
  ]

class SymbolEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('name',    c_ubyte * (SYMBOL_NAME_LIMIT + 1)),
    ('address', c_ushort),
    ('size',    c_ushort),
    ('section', c_ubyte),
  ]

  def get_name(self):
    name = ''

    for i in range(0, SYMBOL_NAME_LIMIT + 1):
      if self.name[i] == 0:
        return name
      name += chr(self.name[i])
    else:
      assert False

  def set_name(self, name):
    for i in range(0, len(name)):
      self.name[i] = ord(name[i])
    self.name[i + 1] = 0

SECTION_ITEM_SIZE = [
  2, 1, 0, sizeof(SymbolEntry)
]

class File(file):
  MAGIC = 0xDEAD
  VERSION = 1

  def __init__(self, *args, **kwargs):
    super(File, self).__init__(*args, **kwargs)

    self.__header = None
    self.__sections = []

    if self.mode == 'rb':
      self.load()

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

  def read_u8(self):
    b = self.read(1)
    u = struct.unpack('<B', b)
    debug('read_u8:', u[0])
    return UInt8(u[0])

  def read_u16(self):
    b = self.read(2)
    u = struct.unpack('<H', b)
    debug('read_u16:', u[0])
    return UInt16(u[0])

  def read_u32(self):
    b = self.read(4)
    u = struct.unpack('<I', b)
    debug('read_u32:', u[0])
    return UInt32(u[0])

  def write_u8(self, value):
    debug('write_u8:', value)
    self.write(struct.pack('<B', value))

  def write_u16(self, value):
    debug('write_u16:', value)
    self.write(struct.pack('<H', value))

  def write_u32(self, value):
    debug('write_u32:', value)
    self.write(struct.pack('<I', value))

  def load(self):
    self.seek(0)

    debug('load: file header')

    self.__header = FileHeader()
    self.__header.magic = self.read_u16().u16

    if self.__header.magic != self.MAGIC:
      error('load: magic cookie not recognized!')
      raise cpu.errors.MalformedBinaryError('Magic cookie not recognized!')

    self.__header.version = self.read_u16().u16
    self.__header.sections = self.read_u16().u16

    for i in range(0, self.__header.sections):
      header = SectionHeader()
      header.index = i

      debug('load: section header #%i' % header.index)

      header.type = self.read_u8().u8
      header.flags = self.read_u8().u8
      header.base = self.read_u16().u16
      header.size = self.read_u16().u16
      header.offset = self.read_u32().u32
      self.__sections.append((header, []))

    for i in range(0, self.__header.sections):
      header, content = self.__sections[i]

      debug('load: section content #%i' % header.index)

      self.seek(header.offset)

      i = 0
      while i < header.size:
        if header.type == SectionTypes.DATA:
          content.append(self.read_u8())

        elif header.type == SectionTypes.SYMBOLS:
          se = SymbolEntry()
          content.append(se)

          for k in range(0, SYMBOL_NAME_LIMIT + 1):
            se.name[k] = self.read_u8().u8
          se.address = self.read_u16().u16
          se.size = self.read_u16().u16
          se.section = self.read_u8().u8

        else:
          ins = cpu.instructions.InstructionBinaryFormat()
          ins.generic.ins = self.read_u16().u16
          content.append(ins)

          if 'l' in cpu.instructions.INSTRUCTIONS[ins.nullary.opcode].args:
            content.append(self.read_u16())
            i += 1

        i += 1

  def save(self):
    self.seek(0)

    self.__header.sections = len(self.__sections)

    offset = sizeof(FileHeader) + sizeof(SectionHeader) * self.__header.sections

    symbol_sections = []

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      if header.type == SectionTypes.SYMBOLS:
        symbol_sections.append(header)

      if header.type == SectionTypes.STACK:
        header.size = 0
        header.offset = 0
      else:
        header.size = len(content)
        header.offset = offset

      offset += header.size * SECTION_ITEM_SIZE[header.type]

    debug('save: file header')

    self.write_u16(self.__header.magic)
    self.write_u16(self.__header.version)
    self.write_u16(self.__header.sections)

    for i in range(0, len(self.__sections)):
      header = self.__sections[i][0]

      debug('save: section header #%i' % header.index)

      self.write_u8(header.type)
      self.write_u8(header.flags)
      self.write_u16(header.base)
      self.write_u16(header.size)
      self.write_u32(header.offset)

    for i in range(0, len(self.__sections)):
      header, content = self.__sections[i]

      debug('save: section content #%i' % header.index)

      if header.type == SectionTypes.STACK:
        debug('save:  STACK section does not have content, skipped')
        continue

      self.seek(header.offset)

      for j in range(0, len(content)):
        if type(content[j]) == cpu.instructions.InstructionBinaryFormat:
          self.write_u16(content[j].generic.ins)

        elif type(content[j]) == SymbolEntry:
          se = content[j]

          for k in range(0, SYMBOL_NAME_LIMIT + 1):
            self.write_u8(se.name[k])
          self.write_u16(se.address)
          self.write_u16(se.size)
          self.write_u8(se.section)

        elif type(content[j]) == UInt16:
          self.write_u16(content[j].u16)

        elif type(content[j]) == UInt8:
          self.write_u8(content[j].u8)

        else:
          assert False

