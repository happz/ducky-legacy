import ctypes
import enum
import mmap

from ctypes import LittleEndianStructure, Union, c_ubyte, c_ushort, c_uint

from cpu.errors import *
from util import *

###
### Memory layout
###
#
# 0x0000    IRQ table address   (0x0100 by default)
# 0x0002    INT table address   (0x0200 by default)
# 0x0004    Memory map address  (0x0300 by default)
# 0x0006    Boot IP map address (0x0400 by default)
# ......
# 0x0100    IRQ table
# 0x0200    INT table
# 0x0300    Memory map
# 0x0400    Boot IP map
# ......
# 0x0500    First boot ip
# ......
# 0xFFFF    Default SP

MEM_HEADER_ADDRESS      = 0x0
MEM_IRQ_TABLE_ADDRESS   = 0x0100
MEM_INT_TABLE_ADDRESS   = 0x0200
MEM_MEMORY_MAP_ADDRESS  = 0x0300
MEM_BOOT_IP_MAP_ADDRESS = 0x0400

MEM_FIRST_BOOT_IP       = 0x0500

MEM_FIRST_SP            = 0xFFFF

PAGE_SHIFT = 8
PAGE_SIZE = (1 << PAGE_SHIFT)
PAGE_MASK = (~(PAGE_SIZE - 1))

class UInt8(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [('u8', c_ubyte)]

class UInt16(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u16', c_ushort)
  ]

class UInt32(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u32', c_uint)
  ]

class MemoryHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('irq_table_address',   c_ushort),
    ('int_table_address',   c_ushort),
    ('memory_map_address',  c_ushort),
    ('boot_ip_map_address', c_ushort)
  ]

class MemoryMapEntry_overall(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [('u8', c_ubyte)]

class MemoryMapEntry_flags(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('read',    c_ubyte, 1),
    ('write',   c_ubyte, 1),
    ('execute', c_ubyte, 1),
    ('dirty',   c_ubyte, 1),
    ('__reserved__', c_ubyte, 4)
  ]

class MemoryMapEntry(Union):
  _pack_ = 0
  _fields_ = [
    ('overall', MemoryMapEntry_overall),
    ('flags',   MemoryMapEntry_flags)
  ]

def mme2str(mme):
  return 'read=%i, write=%i, exec=%i, dirty=%i' % (mme.flags.read, mme.flags.write, mme.flags.execute, mme.flags.dirty)

class MemoryPage(object):
  def __init__(self, controller, index):
    super(MemoryPage, self).__init__()

    self.__controller = controller
    self.index = index
    self.__data = None

  def __init_data(self):
    if not self.__data:
      self.__data = [0 for _ in range(0, PAGE_SIZE)]

  def clear(self):
    for i in range(0, PAGE_SIZE):
      self.__data[i] = 0

  def mme_address(self):
    return self.__controller.header.memory_map_address + self.index

  @property
  def mme(self):
    mme = MemoryMapEntry()
    mme.overall.u8 = self.__controller.read_u8(self.mme_address(), privileged = True).u8

    debug('mp.get_mme: page=0x%X, %s' % (self.index, mme2str(mme)))

    return mme

  @mme.setter
  def mme(self, mme):
    debug('mp.set_mme: page=0x%X, %s' % (self.index, mme2str(mme)))

    self.__controller.write_u8(self.mme_address(), mme.overall.u8, privileged = True, dirty = False)

  def mme_update(self, flag, value):
    debug('mp.mme_update: page=0x%X, flag=%s, value=%i' % (self.index, flag, value))

    mme = self.mme
    setattr(mme.flags, flag, value)
    self.mme = mme

  def readable(self, value):
    self.mme_update('read', value)

  def writable(self, value):
    self.mme_update('write', value)

  def executable(self, value):
    self.mme_update('execute', True)

  def dirty(self, value):
    self.mme_update('dirty', value)
  
  def __check_access(self, offset, access):
    mme = self.mme

    debug('mp.__check_access: page=0x%X, offset=0x%X, access=%s, %s' % (self.index, offset, access, mme2str(mme)))

    if access == 'read' and not mme.flags.read:
      raise AccessViolationError('Not allowed to read from memory: page=%i, addr=%i' % (self.index, offset))

    if access == 'write' and not mme.flags.write:
      raise AccessViolationError('Not allowed to write to memory: page=%i, addr=%i' % (self.index, offset))

    if access == 'execute' and not mme.flags.execute:
      raise AccessViolationError('Not allowed to execute from memory: page=%i, addr=%i' % (self.index, offset))

    return True

  def __len__(self):
    return PAGE_SIZE

  def read_u8(self, offset, privileged = False):
    debug('mp.read_u8: page=0x%X, offset=0x%X, priv=%s' % (self.index, offset, privileged))

    privileged or self.__check_access(offset, 'read')
    self.__init_data()

    return UInt8(self.__data[offset])

  def read_u16(self, offset, privileged = False):
    debug('mp.read_u16: page=0x%X, offset=0x%X, priv=%s' % (self.index, offset, privileged))

    privileged or self.__check_access(offset, 'read')
    self.__init_data()

    if offset & 0x1:
      raise AccessViolationError('Unable to access unaligned address: page=%i, addr=%i' % (self.index, offset))

    return UInt16(self.__data[offset] | self.__data[offset + 1] << 8)

  def write_u8(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u8: page=0x%X, offset=0x%X, value=0x%X, priv=%s' % (self.index, offset, value, privileged))

    privileged or self.__check_access(offset, 'write')
    self.__init_data()

    self.__data[offset] = value
    dirty and self.dirty(True)

  def write_u16(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u16: page=0x%X, offset=0x%X, value=0x%X, priv=%s' % (self.index, offset, value, privileged))

    privileged or self.__check_access(offset, 'write')
    self.__init_data()

    if offset & 0x1:
      raise AccessViolationError('Unable to access unaligned address: page=%i, addr=%i' % (self.index, offset))

    self.__data[offset] = value & 0x00FF
    self.__data[offset + 1] = (value & 0xFF00) >> 8

    dirty and self.dirty(True)

class MemoryController(object):
  def __init__(self, size = 0xFFFF, custom_header = False):
    super(MemoryController, self).__init__()

    self.size = size

    self.__header = None
    self.__pages = [MemoryPage(self, i) for i in range(0, size / PAGE_SIZE)]

  def boot(self):
    # Header
    self.write_u16(MEM_HEADER_ADDRESS,     MEM_IRQ_TABLE_ADDRESS,   privileged = True)
    self.write_u16(MEM_HEADER_ADDRESS + 2, MEM_INT_TABLE_ADDRESS,   privileged = True)
    self.write_u16(MEM_HEADER_ADDRESS + 4, MEM_MEMORY_MAP_ADDRESS,  privileged = True)
    self.write_u16(MEM_HEADER_ADDRESS + 6, MEM_BOOT_IP_MAP_ADDRESS, privileged = True)

    self.__header = None

    # IRQ table

    # INT table

    # Memory map table
    mme = MemoryMapEntry()
    mme.overall.u8 = 0
    for page in self.__pages:
      page.mme = mme

    # Boot IP map
    boot_ip = UInt16()
    boot_ip.u16 = MEM_FIRST_BOOT_IP
    self.write_u16(MEM_BOOT_IP_MAP_ADDRESS, boot_ip.u16, privileged = True)

    # Stack
    self.__pages[-1].readable(True)
    self.__pages[-1].writable(True)

  def mme_update_area(self, address, size, flag, value):
    debug('mc.mme_update_area: address=0x%X, size=0x%X, flag=%s, value=%i' % (address, size, flag, value))

    pages_start = self.addr_to_page(address)
    pages_cnt   = (size / PAGE_SIZE) + 1

    debug('mc.mme_update: start_page=0x%X, pages=%i' % (pages_start, pages_cnt))

    for i in range(pages_start, pages_start + pages_cnt):
      self.__pages[i].mme_update(flag, value)

  def __place_segment_u16(self, sb, s):
    import cpu.instructions

    sp = UInt16(sb.u16)
    size = UInt16(len(s) * 2)

    debug('place segment: sb=0x%X, size=0x%X' % (sb.u16, size.u16))

    for i in s:
      if type(i) == cpu.instructions.InstructionBinaryFormat:
        value = UInt16(i.generic.ins)

      elif type(i) == UInt16:
        value = i

      self.write_u16(sp.u16, value.u16, privileged = True)
      sp.u16 += 2

    self.mme_update_area(sb.u16, size.u16, 'read', True)

  def __place_segment_u8(self, sb, s):
    import cpu.instructions

    sp = UInt16(sb.u16)
    size = UInt16(len(s) * 2)

    debug('place segment: sb=0x%X, size=0x%X' % (sb.u16, size.u16))

    for i in s:
      self.write_u8(sp.u16, i.u8, privileged = True)
      sp.u16 += 1

    self.mme_update_area(sb.u16, size.u16, 'read', True)

  def place_cs(self, csb, cs):
    self.__place_segment_u16(csb, cs)

  def place_ds(self, dsb, ds):
    self.__place_segment_u8(dsb, ds)

  def load_file(self, file_in):
    import mm.binary

    with mm.binary.File(file_in, 'r') as f_in:
      f_in.load()

      f_header = f_in.get_header()

      for i in range(0, f_header.sections):
        s_header, s_content = f_in.get_section(i)

        if s_header.type == mm.binary.SectionTypes.TEXT:
          self.place_cs(UInt16(s_header.base), s_content)

        elif s_header.type == mm.binary.SectionTypes.DATA:
          self.place_ds(UInt16(s_header.base), s_content)

  @property
  def header(self):
    if self.__header:
      return self.__header

    self.__header = header = MemoryHeader()

    header.irq_table_address = self.read_u16(MEM_HEADER_ADDRESS, privileged = True).u16
    header.int_table_address = self.read_u16(MEM_HEADER_ADDRESS + 2, privileged = True).u16
    header.memory_map_address = self.read_u16(MEM_HEADER_ADDRESS + 4, privileged = True).u16
    header.boot_ip_map_address = self.read_u16(MEM_HEADER_ADDRESS + 6, privileged = True).u16

    return header

  def addr_to_page(self, addr):
    return (addr & PAGE_MASK) >> PAGE_SHIFT

  def addr_to_offset(self, addr):
    return (addr & (PAGE_SIZE - 1))

  def read_u8(self, addr, privileged = False):
    debug('mc.read_u8: addr=0x%X, priv=%i' % (addr, privileged))
    return self.__pages[self.addr_to_page(addr)].read_u8(self.addr_to_offset(addr), privileged = privileged)
    
  def read_u16(self, addr, privileged = False):
    debug('mc.read_u16: addr=0x%X, priv=%i' % (addr, privileged))
    return self.__pages[self.addr_to_page(addr)].read_u16(self.addr_to_offset(addr), privileged = privileged)

  def write_u8(self, addr, value, privileged = False, dirty = True):
    debug('mc.write_u8: addr=0x%X, value=0x%X, priv=%i, dirty=%i' % (addr, value, privileged, dirty))
    self.__pages[self.addr_to_page(addr)].write_u8(self.addr_to_offset(addr), value, privileged = privileged, dirty = dirty)

  def write_u16(self, addr, value, privileged = False, dirty = True):
    debug('mc.write_u16: addr=0x%X, value=0x%X, priv=%i, dirty=%i' % (addr, value, privileged, dirty))
    self.__pages[self.addr_to_page(addr)].write_u16(self.addr_to_offset(addr), value, privileged = privileged, dirty = dirty)

