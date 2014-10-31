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
# 0x000000    IRQ table address   (0x000100 by default)
# 0x000002    INT table address   (0x000200 by default)
# 0x000004    Memory map address  (0x000300 by default)
# 0x000006    Segment map address (0x000400 by default)
# ......
# 0x000100    IRQ table
# 0x000200    INT table
# 0x000300    Memory map
# 0x000400    Segment map
# ......

MEM_HEADER_ADDRESS      = 0x000000
MEM_IRQ_TABLE_ADDRESS   = 0x000100
MEM_INT_TABLE_ADDRESS   = 0x000200
MEM_MEMORY_MAP_ADDRESS  = 0x000300
MEM_SEGMENT_MAP_ADDRESS = 0x000400

PAGE_SHIFT = 8
PAGE_SIZE = (1 << PAGE_SHIFT)
PAGE_MASK = (~(PAGE_SIZE - 1))

SEGMENT_SHIFT = 16
SEGMENT_SIZE  = 256 # pages
SEGMENT_PROTECTED = 0 # first segment is already allocated

UINT8_FMT  = lambda v: '0x%02X' % v
UINT16_FMT = lambda v: '0x%04X' % v
UINT24_FMT = lambda v: '0x%06X' % v

PAGE_FMT = lambda page: '%u' % page
SEGM_FMT = lambda segment: UINT8_FMT(segment)
ADDR_FMT = lambda address: UINT24_FMT(address)
SIZE_FMT = lambda size: '%u' % size

class UInt8(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u8', c_ubyte)
  ]

class UInt16(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u16', c_ushort)
  ]

# Yes, this one is larger but it's used only for transporting
# addresses between CPUs and memory controller => segment
# register and u16 have to fit in.
class UInt24(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u24', c_uint)
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
    ('segment_map_address', c_ushort)
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

  def __str__(self):
    return 'read=%i, write=%i, exec=%i, dirty=%i' % (self.flags.read, self.flags.write, self.flags.execute, self.flags.dirty)

class SegmentMapEntry_overall(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u8', c_ubyte)
  ]

class SegmentMapEntry_flags(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('allocated',    c_ubyte, 1),
    ('__reserved__', c_ubyte, 1)
  ]

class SegmentMapEntry(Union):
  _pack_ = 0
  _fields_ = [
    ('overall', SegmentMapEntry_overall),
    ('flags',   SegmentMapEntry_flags)
  ]

def segment_base_addr(segment):
  return segment * SEGMENT_SIZE * PAGE_SIZE

def segment_addr_to_addr(segment, addr):
  return segment_base_addr(segment) + addr

def addr_to_page(addr):
  return (addr & PAGE_MASK) >> PAGE_SHIFT

def addr_to_offset(addr):
  return (addr & (PAGE_SIZE - 1))

def area_to_pages(addr, size):
  return (addr_to_page(addr), (size / PAGE_SIZE) + 1)

class MemoryPage(object):
  def __init__(self, controller, index):
    super(MemoryPage, self).__init__()

    self.controller = controller
    self.index = index

    self.base_address = self.index * PAGE_SIZE

  def mme_address(self):
    return self.controller.header.memory_map_address + self.index

  @property
  def mme(self):
    mme = MemoryMapEntry()
    mme.overall.u8 = self.controller.read_u8(self.mme_address(), privileged = True).u8

    debug('mp.get_mme: page=%s, %s' % (PAGE_FMT(self.index), str(mme)))

    return mme

  @mme.setter
  def mme(self, mme):
    debug('mp.set_mme: page=%s, %s' % (PAGE_FMT(self.index), str(mme)))

    self.controller.write_u8(self.mme_address(), mme.overall.u8, privileged = True, dirty = False)

  def mme_update(self, flag, value):
    debug('mp.mme_update: page=%s, flag=%s, value=%i' % (PAGE_FMT(self.index), flag, value))

    mme = self.mme
    setattr(mme.flags, flag, value)
    self.mme = mme

  def mme_reset(self):
    debug('mp.mme_reset')

    mme = MemoryMapEntry()
    mme.overall.u8 = 0
    self.mme = mme

  def readable(self, value):
    self.mme_update('read', value)

  def writable(self, value):
    self.mme_update('write', value)

  def executable(self, value):
    self.mme_update('execute', True)

  def dirty(self, value):
    self.mme_update('dirty', value)
  
  def check_access(self, offset, access):
    mme = self.mme

    debug('mp.check_access: page=%s, offset=%s, access=%s, %s' % (PAGE_FMT(self.index), ADDR_FMT(offset), access, str(mme)))

    if access == 'read' and not mme.flags.read:
      raise AccessViolationError('Not allowed to read from memory: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    if access == 'write' and not mme.flags.write:
      raise AccessViolationError('Not allowed to write to memory: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    if access == 'execute' and not mme.flags.execute:
      raise AccessViolationError('Not allowed to execute from memory: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return True

  def __len__(self):
    return PAGE_SIZE

  def do_clear(self):
    raise AccessViolationError('Not allowed to clear memory on this address: page=%s' % PAGE_FMT(self.index))

  def do_read_u8(self, offset):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_read_u16(self, offset):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_read_u32(self, offset):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_write_u8(self, offset, value):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_write_u16(self, offset, value):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_write_u32(self, offset, value):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def clear(self, privileged = False):
    debug('mp.clear: page=%s, priv=%s' % (PAGE_FMT(self.index), privileged))

    privileged or self.check_access(offset, 'write')

    self.do_clear()

  def read_u8(self, offset, privileged = False):
    debug('mp.read_u8: page=%s, offset=%sX, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    return self.do_read_u8(offset)

  def read_u16(self, offset, privileged = False):
    debug('mp.read_u16: page=%s, offset=%s, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    return self.do_read_u16(offset)

  def read_u32(self, offset, privileged = False):
    debug('mp.read_u32: page=%s, offset=%s, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    return self.do_read_u32(offset)

  def write_u8(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u8: page=%s, offset=%s, value=%s priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    self.do_write_u8(offset, value)
    dirty and self.dirty(True)

  def write_u16(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u16: page=%s, offset=%s, value=%s, priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    self.do_write_u16(offset, value)

    dirty and self.dirty(True)

  def write_u32(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u32: page=%s, offset=%s, value=%s, priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    self.do_write_u32(offset, value)

    dirty and self.dirty(True)

class AnonymousMemoryPage(MemoryPage):
  def __init__(self, controller, index):
    super(AnonymousMemoryPage, self).__init__(controller, index)

    self.__data = [0 for _ in range(0, PAGE_SIZE)]

  def do_clear(self):
    for i in range(0, PAGE_SIZE):
      self.__data[i] = 0

  def do_read_u8(self, offset):
    debug('mp.do_read_u8: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt8(self.__data[offset])

  def do_read_u16(self, offset):
    debug('mp.do_read_u16: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt16(self.__data[offset] | self.__data[offset + 1] << 8)

  def do_read_u32(self, offset):
    debug('mp.do_read_u32: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt32(self.__data[offset] | self.__data[offset + 1] << 8 | self.__data[offset + 2] << 16 | self.__data[offset + 3] << 24)

  def do_write_u8(self, offset, value):
    debug('mp.do_write_u8: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value)))

    self.__data[offset] = value

  def do_write_u16(self, offset, value):
    debug('mp.do_write_u16: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    self.__data[offset] = value & 0x00FF
    self.__data[offset + 1] = (value & 0xFF00) >> 8

  def do_write_u32(self, offset, value):
    debug('mp.do_write_u32: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    self.__data[offset]     =  value &       0xFF
    self.__data[offset + 1] = (value &     0xFF00) >> 8
    self.__data[offset + 2] = (value &   0xFF0000) >> 16
    self.__data[offset + 3] = (value & 0xFF000000) >> 24

class MMapMemoryPage(MemoryPage):
  def __init__(self, controller, index, data, offset):
    super(MMapMemoryPage, self).__init__(controller, index)

    self.__data = data
    self.__offset = offset

  def do_clear(self):
    for i in range(0, PAGE_SIZE):
      self.__data[i] = 0

  def do_read_u8(self, offset):
    debug('mp.do_read_u8: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt8(self.__data[self.__offset + offset])

  def do_read_u16(self, offset):
    debug('mp.do_read_u16: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt16(self.__data[self.__offset + offset] | self.__data[self.__offset + offset + 1] << 8)

  def do_read_u32(self, offset):
    debug('mp.do_read_u32: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt32(self.__data[self.__offset + offset] | self.__data[self.__offset + offset + 1] << 8 | self.__data[offset + offset + 2] << 16 | self.__data[offset + offset + 3] << 24)

  def do_write_u8(self, offset, value):
    debug('mp.do_write_u8: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value)))

    self.__data[self.__offset + offset] = value

  def do_write_u16(self, offset, value):
    debug('mp.do_write_u16: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    self.__data[self.__offset + offset]     =  value &       0xFF
    self.__data[self.__offset + offset + 1] = (value &     0xFF00) >> 8

  def do_write_u32(self, offset, value):
    self.__data[self.__offset + offset]     =  value &       0xFF
    self.__data[self.__offset + offset + 1] = (value &     0xFF00) >> 8
    self.__data[self.__offset + offset + 2] = (value &   0xFF0000) >> 16
    self.__data[self.__offset + offset + 3] = (value & 0xFF000000) >> 24

class MMapArea(object):
  def __init__(self, address, size, file_path, ptr, pages_start, pages_cnt):
    super(MMapArea, self).__init__()

    self.address = address
    self.size = size
    self.file_path
    self.ptr = ptr
    self.pages_start = pages_start
    self.pages_cnt = pages_cnt

class MemoryController(object):
  def __init__(self, size = 0x1000000, custom_header = False):
    super(MemoryController, self).__init__()

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if size % (SEGMENT_SIZE * PAGE_SIZE) != 0:
      raise InvalidResourceError('Memory size must be multiple of SEGMENT_SIZE')

    self.__header = None

    self.__size = size
    self.__pages_cnt = size / PAGE_SIZE
    self.__pages = {}

    self.__segments_cnt = size / (SEGMENT_SIZE * PAGE_SIZE)
    self.__segments = {}

    # mmap
    self.opened_mmap_files = {} # path: (cnt, file)
    self.mmap_areas = {}

  def alloc_segment(self):
    debug('mc.alloc_segment')

    for i in range(0, self.__segments_cnt):
      if i in self.__segments:
        continue

      # No SegmentMapEntry flags are in use right now, just keep this option open
      debug('mc.alloc_segment: segment=%s' % SEGM_FMT(i))

      self.__segments[i] = True
      return UInt8(i)

    raise InvalidResourceError('No free segment available')

  def get_page(self, index):
    if index not in self.__pages:
      self.__pages[index] = AnonymousMemoryPage(self, index)

    return self.__pages[index]

  def alloc_page(self, segment = None):
    if segment:
      pages_start = segment.u8 * SEGMENT_SIZE
      pages_cnt = SEGMENT_SIZE
    else:
      pages_start = 0
      pages_cnt = self.__pages_cnt

    debug('mc.alloc_page: page=%s, cnt=%s' % (PAGE_FMT(pages_start), SIZE_FMT(pages_cnt)))

    for i in range(pages_start, pages_start + pages_cnt):
      if i not in self.__pages:
        debug('mc.alloc_page: page=%s' % PAGE_FMT(i))
        return i

    raise InvalidResourceError('No free page available')

  def for_each_page(self, pages_start, pages_cnt, fn):
    area_index = 0
    for page_index in range(pages_start, pages_start + pages_cnt):
      fn(page_index, area_index)
      area_index += 1

  def for_each_page_in_area(self, address, size, fn):
    pages_start, pages_cnt = area_to_pages(address, size)

    self.for_each_page(pages_start, pages_cnt, fn)

  def boot(self):
    # Reserve the first segment for system usage
    self.alloc_segment()

    # Header
    self.write_u16(MEM_HEADER_ADDRESS,     MEM_IRQ_TABLE_ADDRESS,   privileged = True, dirty = False)
    self.write_u16(MEM_HEADER_ADDRESS + 2, MEM_INT_TABLE_ADDRESS,   privileged = True, dirty = False)
    self.write_u16(MEM_HEADER_ADDRESS + 4, MEM_MEMORY_MAP_ADDRESS,  privileged = True, dirty = False)
    self.write_u16(MEM_HEADER_ADDRESS + 6, MEM_SEGMENT_MAP_ADDRESS, privileged = True, dirty = False)

    self.__header = None

    # IRQ table
    self.get_page(addr_to_page(MEM_IRQ_TABLE_ADDRESS)).readable(True)

    # INT table
    self.get_page(addr_to_page(MEM_INT_TABLE_ADDRESS)).readable(True)

    # Memory map table
    self.get_page(addr_to_page(MEM_MEMORY_MAP_ADDRESS)).readable(True)

    # Segment map table
    self.get_page(addr_to_page(MEM_SEGMENT_MAP_ADDRESS)).readable(True)

  def mme_update_area(self, address, size, flag, value):
    debug('mc.mme_update_area: address=%s, size=%s, flag=%s, value=%i' % (ADDR_FMT(address), SIZE_FMT(size), flag, value))

    self.for_each_page_in_area(address, size, lambda page_index, area_index: self.get_page(page_index).mme_update(flag, value))

  def mme_update_pages(self, pages_start, pages_cnt, flag, value):
    debug('mc.mme_update_pages: page=%s, cnt=%s, flag=%s, value=%i' % (PAGE_FMT(pages_start), SIZE_FMT(pages_cnt), flag, value))

    self.for_each_page(pages_start, pages_cnt, lambda page_index, area_index: self.get_page(page_index).mme_update(flag, value))

  def mme_reset_area(self, address, size):
    debug('mc.mme_reset_area: address=%s, size=%s' % (ADDR_FMT(address), SIZE_FMT(size)))

    self.for_each_page_in_area(address, size, lambda page_index, area_index: self.get_page(page_index).mme_reset())

  def mme_reset_pages(self, pages_start, pages_cnt):
    debug('mc.mme_reset_pages: page=%s, size=%s' % (PAGE_FMT(pages_start), SIZE_FMT(pages_cnt)))

    self.for_each_page(pages_start, pages_cnt, lambda page_index, area_index: self.get_page(page_index).mme_reset())

  def __load_content_u8(self, segment, base, content):
    bsp  = UInt24(segment_addr_to_addr(segment.u8, base.u16))
    sp   = UInt24(bsp.u24)
    size = UInt16(len(content))

    debug('mc.__load_content_u8: segment=%s, base=%s, size=%s, sp=%s' % (SEGM_FMT(segment.u8), ADDR_FMT(base.u16), SIZE_FMT(size.u16), ADDR_FMT(sp.u24)))

    for i in content:
      self.write_u8(sp.u24, i.u8, privileged = True)
      sp.u24 += 1

    self.mme_reset_area(bsp.u24, size.u16)
    self.mme_update_area(bsp.u24, size.u16, 'read', True)

  def __load_content_u16(self, segment, base, content):
    bsp  = UInt24(segment_addr_to_addr(segment.u8, base.u16))
    sp   = UInt24(bsp.u24)
    size = UInt16(len(content) * 2)

    debug('mc.__load_content_u16: segment=%s, base=%s, size=%s, sp=%s' % (SEGM_FMT(segment.u8), ADDR_FMT(base.u16), SIZE_FMT(size.u16), ADDR_FMT(sp.u24)))

    for i in content:
      self.write_u16(sp.u24, i.u16, privileged = True)
      sp.u24 += 2

    self.mme_reset_area(bsp.u24, size.u16)
    self.mme_update_area(bsp.u24, size.u16, 'read', True)

  def __load_content_u32(self, segment, base, content):
    import cpu.instructions

    bsp = UInt24(segment_addr_to_addr(segment.u8, base.u16))
    sp   = UInt24(bsp.u24)
    size = UInt16(len(content) * 2)

    debug('mc.__load_content_u32: segment=%s, base=%s, size=%s, sp=%s' % (SEGM_FMT(segment.u8), ADDR_FMT(base.u16), SIZE_FMT(size.u16), ADDR_FMT(sp.u24)))

    for i in content:
      i = cpu.instructions.convert_to_master(i)
      self.write_u32(sp.u24, i.overall.u32, privileged = True)
      sp.u24 += 4

    self.mme_reset_area(bsp.u24, size.u16)
    self.mme_update_area(bsp.u24, size.u16, 'read', True)

  def load_text(self, segment, base, content):
    self.__load_content_u32(segment, base, content)

  def load_data(self, segment, base, content):
    self.__load_content_u8(segment, base, content)

  def load_file(self, file_in, csr = None, dsr = None):
    import mm.binary

    # One segment for code and data
    csr = csr or UInt8(self.alloc_segment().u8)
    dsr = dsr or UInt8(csr.u8)

    csb = UInt16(0)
    dsb = UInt16(0)
    sp  = UInt16(0)

    with mm.binary.File(file_in, 'r') as f_in:
      f_in.load()

      f_header = f_in.get_header()

      for i in range(0, f_header.sections):
        s_header, s_content = f_in.get_section(i)

        if s_header.type == mm.binary.SectionTypes.TEXT:
          csb.u16 = s_header.base
          self.load_text(csr, csb, s_content)

        elif s_header.type == mm.binary.SectionTypes.DATA:
          dsb.u16 = s_header.base
          self.load_data(dsr, dsb, s_content)

        elif s_header.type == mm.binary.SectionTypes.STACK:
          stack_page = self.get_page(self.alloc_page(dsr))
          stack_page.mme_update('read', 1)
          stack_page.mme_update('write', 1)
          sp.u16 = stack_page.index * PAGE_SIZE + PAGE_SIZE

    return (csr, csb, dsr, dsb, sp)

  def __get_mmap_fileno(self, file_path):
    if file_path not in self.opened_mmap_files:
      self.opened_mmap_files[file_path] = [0, open(file_path, 'rwb')]

    desc = self.opened_mmap_files[file_path]

    desc[0] += 1
    return desc[1].fileno()

  def __put_mmap_fileno(self, file_path):
    desc = self.opened_mmap_files[file_path]

    desc[0] -= 1
    if desc[0] > 0:
      return

    desc[1].close()
    del self.opened_mmap_files[file_path]

  def mmap_area(self, file_path, offset, size, address, access, shared):
    debug('mc.mmap_area: file=0x08X, offset=%s, size=%s, address=%s, access=%s, shared=%s',
          file_path, offset, SIZE_FMT(size), ADDR_FMT(address), str(access), shared)

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if address % PAGE_SIZE != 0:
      raise InvalidResourceError('MMap area address must be multiple of PAGE_SIZE')

    pages_start, pages_cnt = area_to_pages(address, size)

    def __assert_page_missing(page_index):
      if page_index in self.__pages:
        raise InvalidResourceError('MMap request overlaps with existing pages')

    self.for_each_page(pages_start, pages_cnt, __assert_page_missing)

    mmap_fileno = self.__get_mmap_fileno(file_path)
    mmap_flags = mmap.MAP_SHARED if shared else mmap.MAP_PRIVATE

    mmap_prot = 0
    if access.flags.read:
      mmap_prot |= mmap.PROT_READ
    if access.flags.write:
      mmap_prot |= mmap.PROT_WRITE

    ptr = mmap.mmap(
      self.__opened_mmap_files[file_path].fileno(),
      size,
      flags = mmap_flags,
      prot = mmap_prot,
      offset = offset)

    def __create_mmap_page(page_index, area_index):
      self.__pages[i] = MMapMemoryPage(self, page_index, ptr, area_index * PAGE_SIZE)

    self.for_each_page(pages_start, pages_cnt, __create_mmap_page)

    self.mme_reset_pages(pages_start, pages_cnt)

    if access.flags.read:
      self.mme_update_pages(pages_start, pages_cnt, 'read', 1)
    if access.flags.write:
      self.mme_update_pages(pages_start, pages_cnt, 'write', 1)

    return MMapArea(address, size, file_path, ptr, pages_start, pages_cnt)

  def unmmap_area(self, mmap_area):
    self.mme_reset_pages(mmap_area.pages_start, mmap_area.pages_cnt)

    def __remove_mmap_page(page_index, area_index):
      del self.__pages[page_index]

    self.for_each_page(mmap_area.pages_start, mmap_area.pages_cnt, __remove_mmap_page)

    del self.mmap_areas[mmap_area.address]

    mmap_area.ptr.close()

    self.__put_mmap_fileno(mmap_area.file_path)

  @property
  def header(self):
    if self.__header:
      return self.__header

    self.__header = header = MemoryHeader()

    header.irq_table_address   = self.read_u16(MEM_HEADER_ADDRESS,     privileged = True).u16
    header.int_table_address   = self.read_u16(MEM_HEADER_ADDRESS + 2, privileged = True).u16
    header.memory_map_address  = self.read_u16(MEM_HEADER_ADDRESS + 4, privileged = True).u16
    header.segment_map_address = self.read_u16(MEM_HEADER_ADDRESS + 6, privileged = True).u16

    return header

  def read_u8(self, addr, privileged = False):
    debug('mc.read_u8: addr=%s, priv=%i' % (ADDR_FMT(addr), privileged))

    return self.get_page(addr_to_page(addr)).read_u8(addr_to_offset(addr), privileged = privileged)

  def read_u16(self, addr, privileged = False):
    debug('mc.read_u16: addr=%s, priv=%i' % (ADDR_FMT(addr), privileged))

    if addr % 2:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    return self.get_page(addr_to_page(addr)).read_u16(addr_to_offset(addr), privileged = privileged)

  def read_u32(self, addr, privileged = False):
    debug('mc.read_u32: addr=%s, priv=%i' % (ADDR_FMT(addr), privileged))

    if addr % 4:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    return self.get_page(addr_to_page(addr)).read_u32(addr_to_offset(addr), privileged = privileged)

  def write_u8(self, addr, value, privileged = False, dirty = True):
    debug('mc.write_u8: addr=%s, value=%s, priv=%i, dirty=%i' % (ADDR_FMT(addr), UINT8_FMT(value), privileged, dirty))
    self.get_page(addr_to_page(addr)).write_u8(addr_to_offset(addr), value, privileged = privileged, dirty = dirty)

  def write_u16(self, addr, value, privileged = False, dirty = True):
    debug('mc.write_u16: addr=%s, value=%s, priv=%i, dirty=%i' % (ADDR_FMT(addr), UINT16_FMT(value), privileged, dirty))

    if addr % 2:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    self.get_page(addr_to_page(addr)).write_u16(addr_to_offset(addr), value, privileged = privileged, dirty = dirty)

  def write_u32(self, addr, value, privileged = False, dirty = True):
    debug('mc.write_u32: addr=%s, value=%s, priv=%i, dirty=%i' % (ADDR_FMT(addr), UINT16_FMT(value), privileged, dirty))

    if addr % 4:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    self.get_page(addr_to_page(addr)).write_u32(addr_to_offset(addr), value, privileged = privileged, dirty = dirty)

