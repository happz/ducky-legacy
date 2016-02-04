"""
Hardware Description Table structures.
"""

from ctypes import LittleEndianStructure, sizeof
from enum import IntEnum

from .mm import u16_t, u32_t

#: Magic number present in HDT header
HDT_MAGIC = 0x4D5E6F70

class HDTEntryTypes(IntEnum):
  """
  Types of different HDT entries.
  """

  CPU    = 0
  MEMORY = 1

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
    ('entries', u32_t)
  ]

  @staticmethod
  def create(logger, config):
    logger.debug('HDTHeader.create')

    header = HDTHeader()

    header.magic = HDT_MAGIC
    header.entries = 0

    return header

class HDTEntry(HDTStructure):
  """
  Base class of all HDT entries.

  Each entry has at least two fields, `type` and `length`. Other fields
  depend on type of entry, and follow immediately after `length` field.

  :param u16_t type: type of entry. See :py:class:`ducky.hdt.HDTEntryTypes`.
  :param u16_t length: length of entry, in bytes.
  """

  @classmethod
  def create(cls, entry_type):
    """
    Create instance of HDT entry. Helper method that creates a new instance, and
    sets its common properties.

    :param u16_t entry_type: type of entry. See :py:class:`ducky.hdt.HDTEntryTypes`.
    :rtype: HDTEntry
    :returns: new instance of a :py:class:`ducky.hdt.HDTEntry` subclass.
    """

    entry = cls()

    entry.type = entry_type
    entry.length = sizeof(cls)

    return entry

class HDTEntry_CPU(HDTEntry):
  """
  HDT entry describing CPU configuration.

  :param u16_t nr_cpus: number of CPUs.
  :param u16_t nr_cores: number of cores per CPU.
  """

  _fields_ = [
    ('type',     u16_t),
    ('length',   u16_t),
    ('nr_cpus',  u16_t),
    ('nr_cores', u16_t)
  ]

  @classmethod
  def create(cls, logger, config):
    entry = super(HDTEntry_CPU, cls).create(HDTEntryTypes.CPU)
    entry.nr_cpus = config.getint('machine', 'cpus')
    entry.nr_cores = config.getint('machine', 'cores')

    logger.debug('HDTEntry_CPU.create: nr_cpus=%s, nr_cores=%s', entry.nr_cpus, entry.nr_cores)

    return [entry]

class HDTEntry_Memory(HDTEntry):
  """
  HDT entry describing memory configuration.

  :param u32_t size: size of memory, in bytes.
  """

  _fields_ = [
    ('type',   u16_t),
    ('length', u16_t),
    ('size',   u32_t)
  ]

  @classmethod
  def create(cls, logger, config):
    entry = super(HDTEntry_Memory, cls).create(HDTEntryTypes.MEMORY)
    entry.size = config.getint('memory', 'size', 0x1000000)

    logger.debug('HDTEntry_Memory.create: size=%s', entry.size)

    return [entry]

class HDT(object):
  """
  Root of HDT. Provides methods for creating HDT for a given machine configuration.
  """

  klasses = [
    HDTEntry_Memory,
    HDTEntry_CPU,
  ]

  def __init__(self, logger, config = None):
    self.logger = logger
    self.config = config

    self.header = None
    self.entries = []

  def create(self):
    self.header = HDTHeader.create(self.logger, self.config)

    for klass in HDT.klasses:
      self.entries += klass.create(self.logger, self.config)

    self.header.entries = len(self.entries)

  def size(self):
    """
    Get size of HDT - sum of entries' lengths and length of a header.

    :rtype: int
    :returns: size of HDT, in bytes.
    """

    return sizeof(HDTHeader) + sum([sizeof(entry) for entry in self.entries])
