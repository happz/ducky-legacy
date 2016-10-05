import enum

from six import itervalues, PY2
from six.moves import range

from ..mm import u8_t, u16_t, u32_t, UINT32_FMT
from ..util import BinaryFile, StringTable, Flags, str2bytes, bytes2str
from ..log import get_logger
from ctypes import LittleEndianStructure, sizeof

class SectionFlagsEncoding(LittleEndianStructure):
  _fields_ = [
    ('readable',         u8_t, 1),
    ('writable',         u8_t, 1),
    ('executable',       u8_t, 1),
    ('loadable',         u8_t, 1),
    ('bss',              u8_t, 1),
    ('globally_visible', u8_t, 1),
  ]

class SectionFlags(Flags):
  _encoding = SectionFlagsEncoding
  _flags = [field[0] for field in SectionFlagsEncoding._fields_]
  _labels = 'RWXLBG'

class SectionTypes(enum.IntEnum):
  UNKNOWN  = 0
  PROGBITS = 1
  SYMBOLS  = 2
  STRINGS  = 3
  RELOC    = 4

SECTION_TYPES = [
  'UNKNOWN', 'PROGBITS', 'SYMBOLS', 'STRINGS', 'RELOC'
]

class SymbolDataTypes(enum.IntEnum):
  INT      = 0
  SHORT    = 1
  CHAR     = 2
  BYTE     = 3
  STRING   = 4
  ASCII    = 5
  FUNCTION = 6
  UNKNOWN  = 7

SYMBOL_DATA_TYPES = 'ISCBTAFU'

class FileFlagsEncoding(LittleEndianStructure):
  _fields_ = [
    ('reserved', u16_t, 1)
  ]

class FileFlags(Flags):
  _encoding = FileFlagsEncoding
  _flags = [field[0] for field in FileFlagsEncoding._fields_]
  _labels = 'M'

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',    u16_t),
    ('version',  u16_t),
    ('flags',    FileFlagsEncoding),
    ('sections', u16_t)
  ]

  def __repr__(self):
    return '<FileHeader: magic=0x%04X, version=%d, flags=%s, sections=%d>' % (self.magic, self.version, FileFlags.from_encoding(self.flags).to_string(), self.sections)

class SectionHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index',     u8_t),
    ('name',      u32_t),
    ('type',      u8_t),
    ('flags',     SectionFlagsEncoding),
    ('padding',   u8_t),
    ('base',      u32_t),
    ('data_size', u32_t),
    ('file_size', u32_t),
    ('offset',    u32_t)
  ]

  def __repr__(self):
    return '<SectionHeader: index={}, name={}, type={}, flags={}, base={}, data_size={}, file_size={}, offset={}>'.format(self.index, self.name, self.type, SectionFlags.from_encoding(self.flags).to_string(), UINT32_FMT(self.base), self.data_size, self.file_size, self.offset)

class SymbolFlagsEncoding(LittleEndianStructure):
  _fields_ = [
    ('globally_visible', u16_t, 1)
  ]

class SymbolFlags(Flags):
  _encoding = SymbolFlagsEncoding
  _flags = [field[0] for field in SymbolFlagsEncoding._fields_]
  _labels = 'G'

class SymbolEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('flags',        SymbolFlagsEncoding),
    ('name',         u32_t),
    ('address',      u32_t),
    ('size',         u32_t),
    ('section',      u8_t),
    ('type',         u8_t),
    ('filename',     u32_t),
    ('lineno',       u32_t)
  ]

  def __repr__(self):
    return '<SymbolEntry: section={}, name={}, type={}, addr={}, flags={}, filename={}, lineno={}>'.format(self.section, self.name, SYMBOL_DATA_TYPES[self.type], UINT32_FMT(self.address), SymbolFlags.from_encoding(self.flags).to_string(), self.filename, self.lineno)

class RelocFlagsEncoding(LittleEndianStructure):
  _fields_ = [
    ('relative',     u16_t, 1),
    ('inst_aligned', u16_t, 1)
  ]

class RelocFlags(Flags):
  _encoding = RelocFlagsEncoding
  _flags = [field[0] for field in RelocFlagsEncoding._fields_]
  _labels = 'RI'

class RelocEntry(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('flags',         RelocFlagsEncoding),
    ('name',          u32_t),
    ('patch_add',     u32_t),
    ('patch_address', u32_t),
    ('patch_section', u8_t),
    ('patch_offset',  u8_t),
    ('patch_size',    u8_t)
  ]

  def __repr__(self):
    return '<RelocEntry: flags=%s, name=%s, section=%s, address=%s, offset=%s, size=%s, add=%s>' % (RelocFlags.from_encoding(self.flags).to_string(), self.name, self.patch_section, UINT32_FMT(self.patch_address), self.patch_offset, self.patch_size, self.patch_add)

class Section(object):
  def __init__(self, parent, index, name = None, header = None, payload = None):
    self.parent = parent
    self.index = index

    self._name = name

    self._header = header
    self._payload = payload

    self._logger = get_logger()
    self.DEBUG = self._logger.debug

  def __repr__(self):
    return '<Section: name=%s, header=%s, payload-len=%s>' % (self._name, self._header, len(self._payload) if self._payload is not None else 'None')

  @property
  def name(self):
    if self._name is None:
      self._name = self.parent.string_table.get_string(self.header.name)

    return self._name

  def _read_header(self):
    self.DEBUG('%s._read_header: index=%d', self.__class__.__name__, self.index)

    self.parent.seek(sizeof(FileHeader) + self.index * sizeof(SectionHeader))
    self._header = self.parent.read_struct(SectionHeader)

  def _create_header(self):
    self.DEBUG('%s._create_header: index=%d', self.__class__.__name__, self.index)

    h = SectionHeader()
    h.index = self.index

    self._header = h

  def _write_header(self):
    assert self._header is not None

    self.DEBUG('%s._write_header: header=%s', self.__class__.__name__, self._header)

    self.parent.seek(sizeof(FileHeader) + self.index * sizeof(SectionHeader))
    self.parent.write_struct(self._header)

  @property
  def header(self):
    if self._header is None:
      if 'r' in self.parent.mode:
        self._read_header()

      else:
        self._create_header()

    return self._header

  def _read_payload(self):
    self.parent.seek(self.header.offset)

    if self.header.type == SectionTypes.SYMBOLS:
      self._payload = [self.parent.read_struct(SymbolEntry) for _ in range(0, self.header.file_size // sizeof(SymbolEntry))]
      return

    if self.header.type == SectionTypes.RELOC:
      self._payload = [self.parent.read_struct(RelocEntry) for _ in range(0, self.header.file_size // sizeof(RelocEntry))]
      return

    if PY2:
      self._payload = bytearray([ord(c) for c in self.parent.read(self.header.file_size)])

    else:
      self._payload = bytearray(self.parent.read(self.header.file_size))

  def _create_payload(self):
    if self.header.type in (SectionTypes.PROGBITS, SectionTypes.STRINGS):
      self._payload = bytearray()
    else:
      self._payload = []

  def _write_payload(self):
    assert self._payload is not None

    self.parent.seek(self.header.offset)

    if self.header.type in (SectionTypes.PROGBITS, SectionTypes.STRINGS):
      if self.header.flags.bss == 1:
        return

      self.parent.write(self._payload)
      return

    if self.header.type in (SectionTypes.SYMBOLS, SectionTypes.RELOC):
      for entry in self._payload:
        self.parent.write_struct(entry)

      return

    from ..mm import MalformedBinaryError
    raise MalformedBinaryError('Unknown section header type {}'.format(self.header.type))

  def _get_payload(self):
    if self._payload is None:
      if 'r' in self.parent.mode:
        self._read_payload()

      else:
        self._create_payload()

    return self._payload

  def _set_payload(self, payload):
    self._payload = payload

  payload = property(_get_payload, _set_payload)

  def prepare_write(self):
    self.DEBUG('%s.prepare_write: name=%s', self.__class__.__name__, self.name)

    if self.header.type == SectionTypes.STRINGS:
      self._payload = str2bytes(self.parent.string_table.buff)

    if self.header.type in (SectionTypes.PROGBITS, SectionTypes.STRINGS) and self.header.flags.bss != 1:
      self.header.file_size = len(self._payload)

    else:
      if self._payload:
        self.header.file_size = len(self._payload) * sizeof(self._payload[0])
      else:
        self.header.file_size = 0

  def write(self):
    assert self._header is not None
    assert self._payload is not None, self._header
    assert self._header.offset != 0

    self._write_header()
    self._write_payload()

class File(BinaryFile):
  MAGIC = 0xDEAD
  VERSION = 3

  @staticmethod
  def open(*args, **kwargs):
    return BinaryFile.do_open(*args, klass = File, **kwargs)

  def setup(self):
    self._header = None

    self._sections = {}

    self._string_section = None
    self._string_table = None

    self.DEBUG = get_logger().debug

    self._orig_read, self.read = self.read, self._read
    self._orig_write, self.write = self.write, self._write

  def _read(self, *args, **kwargs):
    self.DEBUG('%s: _read: %s: %s %s', self.name, self.tell(), args, kwargs)

    return self._orig_read(*args, **kwargs)

  def _write(self, *args, **kwargs):
    self.DEBUG('%s: write: %s: %s %s', self.name, self.tell(), args, kwargs)

    return self._orig_write(*args, **kwargs)

  #
  # File header
  #
  def _read_header(self):
    self.DEBUG('%s: _read_header', self.name)

    self.seek(0)
    return self.read_struct(FileHeader)

  def _create_header(self):
    self.DEBUG('%s: _create_header', self.name)

    h = FileHeader()
    h.magic = self.MAGIC
    h.version = self.VERSION
    h.sections = 0

    self.DEBUG('  %s', h)

    return h

  def _write_header(self, header):
    assert self._header is not None

    self.DEBUG('%s: _write_header', self.name)

    self.seek(0)
    self.write_struct(header)

  @property
  def header(self):
    if self._header is None:
      if 'r' in self.mode:
        self._header = self._read_header()

      else:
        self._header = self._create_header()

    if self._header.magic != self.MAGIC:
      self.ERROR('%s: magic cookie not recognized!', self.name)

      from ..mm import MalformedBinaryError
      raise MalformedBinaryError('Magic cookie not recognized!')

    return self._header

  # Sections
  def create_section(self, name = None):
    self.DEBUG('%s: create_section: name=%s', self.name, name)

    header = SectionHeader()
    header.index = len(self._sections)

    section = Section(self, len(self._sections), name = name, header = header)
    self._sections[header.index] = section
    self.header.sections = len(self._sections)

    return section

  def get_section_by_index(self, index):
    if index not in self._sections:
      self._sections[index] = Section(self, index)

    return self._sections[index]

  def get_section_by_name(self, name, dont_create = False):
    self.DEBUG('%s: get_section_by_name: name=%s', self.name, name)

    for i in range(0, self.header.sections):
      section = self.get_section_by_index(i)

      if section.name is None:
        section.name = self.string_table.get_string(section.header.name)
        self._sections_by_name[section.name] = section

      if section.name == name:
        return section

    if 'r' in self.mode or dont_create is True:
      from ..mm import MalformedBinaryError
      raise MalformedBinaryError('Unknown section named "%s"' % name)

    return self.create_section(name = name)

  def get_section_by_type(self, typ):
    for i in range(0, self.header.sections):
      section = self.get_section_by_index(i)

      if section.header.type == typ:
        return section

    from ..mm import MalformedBinaryError
    raise MalformedBinaryError('Unknown section of type %s' % typ)

  def get_strings_section(self):
    self.DEBUG('%s: get_strings_section', self.name)

    if self._string_section is None:
      if 'r' in self.mode:
        self._string_section = self.get_section_by_type(SectionTypes.STRINGS)

      else:
        self.DEBUG('  string section does not exist')

        section = self.create_section(name = '.strings')
        section.header.type = SectionTypes.STRINGS
        section.header.flags = SectionFlags.create().to_encoding()
        section.payload = bytearray()

        self._string_section = section

        section.header.name = self.string_table.put_string('.strings')

    else:
      self.DEBUG('  string section cached')

    return self._string_section

  #
  # String table
  #
  @property
  def string_table(self):
    if self._string_table is None:
      # If there was no strings section thsi may trigger its creation - check again.
      strings_section = self.get_strings_section()

      if self._string_table is None:
        self._string_table = StringTable(buff = bytes2str(strings_section.payload))

    return self._string_table

  @property
  def sections(self):
    return (self.get_section_by_index(i) for i in range(0, self.header.sections))

  def fix_offsets(self):
    assert 'w' in self.mode

    for index in range(0, self.header.sections):
      self.get_section_by_index(index).prepare_write()

    offset = sizeof(FileHeader) + self.header.sections * sizeof(SectionHeader)

    for index in range(0, self.header.sections):
      section = self.get_section_by_index(index)
      section.header.offset = offset

      offset += section.header.file_size

  def save(self):
    self.fix_offsets()

    self._write_header(self.header)

    for section in itervalues(self._sections):
      section.write()
