"""
Hardware Description Table structures.
"""

from ctypes import LittleEndianStructure, sizeof
from enum import IntEnum

from .mm import u8_t, u16_t, u32_t
from .util import str2int
from .devices import get_driver

#: Magic number present in HDT header
HDT_MAGIC = 0x4D5E6F70

def encode_string(struct, field, s, max_length):
  """
  Store string in a structure's field, and set the corresponding length
  field properly.

  :param HDTStructure struct: structure to modify.
  :param str field: name of field the string should be stored in.
  :param str s: string to encode.
  :param int max_length: maximal number of bytes that can fit into the field.
  """

  for i, c in enumerate(s):
    getattr(struct, field)[i] = ord(c)

    if i == max_length - 1:
      break

  setattr(struct, field + '_length', i + 1)

class HDTEntryTypes(IntEnum):
  """
  Types of different HDT entries.
  """

  UNDEFINED = 0
  CPU       = 1
  MEMORY    = 2
  ARGUMENT  = 3
  DEVICE    = 4

class HDTStructure(LittleEndianStructure):
  """
  Base class of all HDT structures.
  """

  _pack_ = 0

class HDTHeader(HDTStructure):
  """
  HDT header. Contains magic number, number of HDT entries that immediately
  follow header.
  """

  _fields_ = [
    ('magic',   u32_t),
    ('entries', u32_t),
    ('length',  u32_t)
  ]

  def __init__(self):
    HDTStructure.__init__(self)

    self.magic = HDT_MAGIC
    self.entries = 0

class HDTEntry(HDTStructure):
  """
  Base class of all HDT entries.

  Each entry has at least two fields, `type` and `length`. Other fields
  depend on type of entry, and follow immediately after `length` field.

  :param u16_t type: type of entry. See :py:class:`ducky.hdt.HDTEntryTypes`.
  :param u16_t length: length of entry, in bytes.
  """

  ENTRY_HEADER = [
    ('type',   u16_t),
    ('length', u16_t)
  ]

  def __init__(self, entry_type, length):
    HDTStructure.__init__(self)

    self.type = entry_type
    self.length = length

  @classmethod
  def create(cls, *args, **kwargs):
    return [cls(*args, **kwargs)]

class HDTEntry_CPU(HDTEntry):
  """
  HDT entry describing CPU configuration.

  :param u16_t nr_cpus: number of CPUs.
  :param u16_t nr_cores: number of cores per CPU.
  """

  _fields_ = HDTEntry.ENTRY_HEADER + [
    ('nr_cpus',  u16_t),
    ('nr_cores', u16_t)
  ]

  def __init__(self, logger, config):
    HDTEntry.__init__(self, HDTEntryTypes.CPU, sizeof(HDTEntry_CPU))

    self.nr_cpus = config.getint('machine', 'cpus')
    self.nr_cores = config.getint('machine', 'cores')

    logger.debug('HDTEntry_CPU: nr_cpus=%s, nr_cores=%s', self.nr_cpus, self.nr_cores)

class HDTEntry_Memory(HDTEntry):
  """
  HDT entry describing memory configuration.

  :param u32_t size: size of memory, in bytes.
  """

  _fields_ = HDTEntry.ENTRY_HEADER + [
    ('size',   u32_t)
  ]

  def __init__(self, logger, config):
    HDTEntry.__init__(self, HDTEntryTypes.MEMORY, sizeof(HDTEntry_Memory))

    self.size = config.getint('memory', 'size', 0x1000000)

    logger.debug('HDTEntry_Memory: size=%s', self.size)

class HDTEntry_Argument(HDTEntry):
  """
  """

  _fields_ = HDTEntry.ENTRY_HEADER + [
    ('name_length',  u8_t),
    ('value_length', u8_t),
    ('name',         u8_t * 13),
    ('value',        u8_t * 13)
  ]

  MAX_NAME_LENGTH = 13

  def __init__(self, arg_name, arg_type, arg_value):
    HDTEntry.__init__(self, HDTEntryTypes.ARGUMENT, sizeof(HDTEntry_Argument))

    encode_string(self, 'name', arg_name, HDTEntry_Argument.MAX_NAME_LENGTH)

    if arg_type == 'int':
      arg_value = str2int(arg_value)

      self.value[0] = arg_value & 0xFF
      self.value[1] = (arg_value >> 8) & 0xFF
      self.value[2] = (arg_value >> 16) & 0xFF
      self.value[3] = (arg_value >> 24) & 0xFF

    else:
      encode_string(self, 'value', arg_value, HDTEntry_Argument.MAX_NAME_LENGTH)

  @classmethod
  def create(cls, logger, config):
    if not config.has_section('arguments'):
      return []

    arguments = []

    for arg_name in config.options('arguments'):
      arg_type, arg_value = config.get('arguments', arg_name).split(',')
      arg_type = arg_type.strip()
      arg_value = arg_value.strip()

      arguments.append(HDTEntry_Argument(arg_name, arg_type, arg_value))

    return arguments

class HDTEntry_Device(HDTEntry):
  """
  """

  MAX_NAME_LENGTH = 10
  MAX_IDENT_LENGTH = 32

  ENTRY_HEADER = HDTEntry.ENTRY_HEADER + [
    ('name_length',  u8_t),
    ('flags',        u8_t),
    ('name',         u8_t * MAX_NAME_LENGTH),
    ('ident',        u8_t * MAX_IDENT_LENGTH)
  ]

  def __init__(self, logger, name, ident):
    HDTEntry.__init__(self, HDTEntryTypes.DEVICE, sizeof(self.__class__))

    encode_string(self, 'name', name, HDTEntry_Device.MAX_NAME_LENGTH)
    encode_string(self, 'ident', ident, HDTEntry_Device.MAX_IDENT_LENGTH)

class HDT(object):
  """
  Root of HDT. Provides methods for creating HDT for a given machine configuration.

  :param logging.Logger logger: logger instance used for logging.
  :param ducky.config.MachineConfig config: configuration file HDT should reflect.
  """

  #: These HDT entries are added automatically.
  klasses = [
    HDTEntry_Memory,
    HDTEntry_CPU,
    HDTEntry_Argument
  ]

  def __init__(self, logger, config = None):
    self.logger = logger
    self.config = config

    self.header = None
    self.entries = []

  def __len__(self):
    """
    Get size of HDT - sum of entries' lengths and length of a header.

    :rtype: int
    :returns: size of HDT, in bytes.
    """

    return sizeof(HDTHeader) + sum([sizeof(entry) for entry in self.entries])

  def create(self):
    """
    Create HDT header and entries from config file.
    """

    self.header = HDTHeader()

    for klass in HDT.klasses:
      self.entries += klass.create(self.logger, self.config)

    for device in self.config.iter_devices():
      self.entries += get_driver(self.config.get(device, 'driver', None)).create_hdt_entries(self.logger, self.config, device)

    self.header.entries = len(self.entries)
    self.header.length = len(self)
