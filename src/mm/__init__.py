import ctypes
import enum
import mmap
import threading

from ctypes import LittleEndianStructure, Union, c_ubyte, c_ushort, c_uint, sizeof

from cpu.errors import InvalidResourceError, AccessViolationError
from util import debug

MEM_IRQ_TABLE_ADDRESS   = 0x000000
MEM_INT_TABLE_ADDRESS   = 0x000100

PAGE_SHIFT = 8
PAGE_SIZE = (1 << PAGE_SHIFT)
PAGE_MASK = (~(PAGE_SIZE - 1))

SEGMENT_SHIFT = 16
SEGMENT_SIZE  = 256 # pages
SEGMENT_PROTECTED = 0 # first segment is already allocated

def __var_to_int(v):
  if type(v) == UInt8:
    return v.u8

  if type(v) == UInt16:
    return v.u16

  if type(v) == UInt24:
    return v.u24

  if type(v) == UInt32:
    return v.u32

  return v

UINT8_FMT  = lambda v: '0x%02X' % (__var_to_int(v) & 0xFF)
UINT16_FMT = lambda v: '0x%04X' % (__var_to_int(v) & 0xFFFF)
UINT24_FMT = lambda v: '0x%06X' % (__var_to_int(v) & 0xFFFFFF)
UINT32_FMT = lambda v: '0x%08X' % __var_to_int(v)

PAGE_FMT = lambda page: '%u' % page
SEGM_FMT = lambda segment: UINT8_FMT(segment)
ADDR_FMT = lambda address: UINT24_FMT(address)
SIZE_FMT = lambda size: '%u' % size

def OFFSET_FMT(offset):
  s = '-' if offset < 0 else ''

  return '%s0x%04X' % (s, abs(offset))

class UInt8(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u8', c_ubyte)
  ]

  def __repr__(self):
    return '<UInt8: %u>' % self.u8

class UInt16(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u16', c_ushort)
  ]

  def __repr__(self):
    return '<UInt16: %u>' % self.u16

# Yes, this one is larger but it's used only for transporting
# addresses between CPUs and memory controller => segment
# register and u16 have to fit in.
class UInt24(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u24', c_uint, 24)
  ]

class UInt32(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u32', c_uint)
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

def buff_to_uint16(buff, offset):
  return UInt16(buff[offset] | buff[offset + 1] << 8)

def buff_to_uint32(buff, offset):
  return UInt32(buff[offset] | buff[offset + 1] << 8 | buff[offset + 2] << 16 | buff[offset + 3] << 24)

def uint16_to_buff(i, buff, offset):
  buff[offset]     =  i & 0x00FF
  buff[offset + 1] = (i & 0xFF00) >> 8

def uint32_to_buff(i, buff, offset):
  buff[offset]     =  i &       0xFF
  buff[offset + 1] = (i &     0xFF00) >> 8
  buff[offset + 2] = (i &   0xFF0000) >> 16
  buff[offset + 3] = (i & 0xFF000000) >> 24

def get_code_entry_address(s_header, s_content):
  for entry in s_content:
    if hasattr(entry, 'get_name') and entry.get_name() != 'main':
      continue

    if hasattr(entry, 'name') and entry.name.name != 'main':
      continue

    debug('"main" function found, use as an entry point')

    return UInt16(entry.address) if hasattr(entry, 'address') else entry.section_ptr

  else:
    return None

class MemoryPage(object):
  def __init__(self, controller, index):
    super(MemoryPage, self).__init__()

    self.controller = controller
    self.index = index

    self.base_address = self.index * PAGE_SIZE
    self.segment_address = self.base_address % (SEGMENT_SIZE * PAGE_SIZE)

    self.lock = threading.RLock()

    self.read    = False
    self.write   = False
    self.execute = False
    self.dirty   = False

  def save_state(self, state):
    debug('mp.save_state')

    from core import MemoryPageState
    page_state = MemoryPageState()

    page_state.index = self.index

    for i in range(0, PAGE_SIZE):
      page_state.content[i] = self.data[i]

    page_state.read = 1 if self.read else 0
    page_state.write = 1 if self.write else 0
    page_state.execute = 1 if self.execute else 0
    page_state.dirty = 1 if self.dirty else 0

    state.mm_page_states.append(page_state)

  def load_state(self, state):
    for i in range(0, PAGE_SIZE):
      self.data[i] = state.content[i]

    self.read = True if state.read == 1 else 0
    self.write = True if state.write == 1 else 0
    self.execute = True if state.execute == 1 else 0
    self.dirty = True if state.dirty == 1 else 0

  def flags_reset(self):
    self.read = False
    self.write = False
    self.execute = False
    self.dirty = False

  def flags_str(self):
    return ''.join([
      'R' if self.read else '-',
      'W' if self.write else '-',
      'X' if self.execute else '-',
      'D' if self.dirty else '-'
    ])

  def check_access(self, offset, access):
    debug('mp.check_access: page=%s, offset=%s, access=%s, %s' % (PAGE_FMT(self.index), ADDR_FMT(offset), access, self.flags_str()))

    if access == 'read' and not self.read:
      raise AccessViolationError('Not allowed to read from memory: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    if access == 'write' and not self.write:
      raise AccessViolationError('Not allowed to write to memory: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    if access == 'execute' and not self.execute:
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

  def do_read_block(self, offset, size):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def do_write_block(self, offset, size, buff):
    raise AccessViolationError('Not allowed to access memory on this address: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

  def clear(self, privileged = False):
    debug('mp.clear: page=%s, priv=%s' % (PAGE_FMT(self.index), privileged))

    privileged or self.check_access(self.base_address, 'write')

    self.do_clear()

  def read_u8(self, offset, privileged = False):
    debug('mp.read_u8: page=%s, offset=%sX, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    with self.lock:
      return self.do_read_u8(offset)

  def read_u16(self, offset, privileged = False):
    debug('mp.read_u16: page=%s, offset=%s, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    with self.lock:
      return self.do_read_u16(offset)

  def read_u32(self, offset, privileged = False):
    debug('mp.read_u32: page=%s, offset=%s, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), privileged))

    privileged or self.check_access(offset, 'read')

    with self.lock:
      return self.do_read_u32(offset)

  def write_u8(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u8: page=%s, offset=%s, value=%s priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    with self.lock:
      self.do_write_u8(offset, value)
      if dirty:
        self.dirty = True

  def write_u16(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u16: page=%s, offset=%s, value=%s, priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    with self.lock:
      self.do_write_u16(offset, value)
      if dirty:
        self.dirty = True

  def write_u32(self, offset, value, privileged = False, dirty = True):
    debug('mp.write_u32: page=%s, offset=%s, value=%s, priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    with self.lock:
      self.do_write_u32(offset, value)
      if dirty:
        self.dirty = True

  def read_block(self, offset, size, privileged = False):
    debug('mp.read_block: page=%s, offset=%s, size=%s, priv=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(size), privileged))

    privileged or self.check_access(offset, 'read')

    with self.lock:
      return self.do_read_block(offset, size)

  def write_block(self, offset, size, buff, privileged = False, dirty = True):
    debug('mp.write_block: page=%s, offset=%s, size=%s, priv=%s, dirty=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(size), privileged, dirty))

    privileged or self.check_access(offset, 'write')

    with self.lock:
      self.do_write_block(offset, size, buff)
      if dirty:
        self.dirty = True

class AnonymousMemoryPage(MemoryPage):
  def __init__(self, controller, index):
    super(AnonymousMemoryPage, self).__init__(controller, index)

    self.data = [0 for _ in range(0, PAGE_SIZE)]

  def do_clear(self):
    for i in range(0, PAGE_SIZE):
      self.data[i] = 0

  def do_read_u8(self, offset):
    debug('mp.do_read_u8: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt8(self.data[offset])

  def do_read_u16(self, offset):
    debug('mp.do_read_u16: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return buff_to_uint16(self.data, offset)

  def do_read_u32(self, offset):
    debug('mp.do_read_u32: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return buff_to_uint32(self.data, offset)

  def do_write_u8(self, offset, value):
    debug('mp.do_write_u8: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value)))

    self.data[offset] = value

  def do_write_u16(self, offset, value):
    debug('mp.do_write_u16: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    uint16_to_buff(value, self.data, offset)

  def do_write_u32(self, offset, value):
    debug('mp.do_write_u32: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    uint32_to_buff(value, self.data, offset)

  def do_read_block(self, offset, size):
    return self.data[offset:offset + size]

  def do_write_block(self, offset, size, buff):
    for i in range(offset, offset + size):
      self.data[offset + i] = buff[i]

class MMapMemoryPage(MemoryPage):
  def __init__(self, controller, index, data, offset):
    super(MMapMemoryPage, self).__init__(controller, index)

    self.data = data
    self.__offset = offset

  def save_state(self, state):
    pass

  def load_state(self, state):
    pass

  def do_clear(self):
    for i in range(0, PAGE_SIZE):
      self.data[i] = 0

  def do_read_u8(self, offset):
    debug('mp.do_read_u8: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt8(self.data[self.__offset + offset])

  def do_read_u16(self, offset):
    debug('mp.do_read_u16: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt16(self.data[self.__offset + offset] | self.data[self.__offset + offset + 1] << 8)

  def do_read_u32(self, offset):
    debug('mp.do_read_u32: page=%s, offset=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset)))

    return UInt32(self.data[self.__offset + offset] | self.data[self.__offset + offset + 1] << 8 | self.data[offset + offset + 2] << 16 | self.data[offset + offset + 3] << 24)

  def do_write_u8(self, offset, value):
    debug('mp.do_write_u8: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT8_FMT(value)))

    self.data[self.__offset + offset] = value

  def do_write_u16(self, offset, value):
    debug('mp.do_write_u16: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    uint16_to_buff(value, self.data, self.__offset + offset)

  def do_write_u32(self, offset, value):
    debug('mp.do_write_u32: page=%s, offset=%s, value=%s' % (PAGE_FMT(self.index), ADDR_FMT(offset), UINT16_FMT(value)))

    uint32_to_buff(value, self.data, self.__offset + offset)

  def do_read_block(self, offset, size):
    return self.data[self.__offset + offset:self.__offset + offset + size]

  def do_write_block(self, offset, size, buff):
    for i in range(self.__offset + offset, self.__offset + offset + size):
      self.data[self.__offset + i] = buff[i]

class MMapArea(object):
  def __init__(self, address, size, file_path, ptr, pages_start, pages_cnt):
    super(MMapArea, self).__init__()

    self.address = address
    self.size = size
    self.file_path = file_path
    self.ptr = ptr
    self.pages_start = pages_start
    self.pages_cnt = pages_cnt

class MemoryController(object):
  def __init__(self, size = 0x1000000):
    super(MemoryController, self).__init__()

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if size % (SEGMENT_SIZE * PAGE_SIZE) != 0:
      raise InvalidResourceError('Memory size must be multiple of SEGMENT_SIZE')

    self.__size = size
    self.__pages_cnt = size / PAGE_SIZE
    self.__pages = {}

    self.__segments_cnt = size / (SEGMENT_SIZE * PAGE_SIZE)
    self.__segments = {}

    # mmap
    self.opened_mmap_files = {} # path: (cnt, file)
    self.mmap_areas = {}

    # pages allocation
    self.lock = threading.RLock()

    self.irq_table_address = MEM_IRQ_TABLE_ADDRESS
    self.int_table_address = MEM_INT_TABLE_ADDRESS

  def save_state(self, state):
    debug('mc.save_state')

    from core import MemoryState, MemorySegmentState
    state.mm_state = mm_state = MemoryState()

    mm_state.size = self.__size
    mm_state.irq_table_address = self.irq_table_address
    mm_state.int_table_address = self.int_table_address

    for segment in self.__segments.keys():
      state.mm_segment_states.append(MemorySegmentState(segment))

    for page in self.__pages.values():
      page.save_state(state)

    mm_state.segments = len(state.mm_segment_states)
    mm_state.pages = len(state.mm_page_states)

  def load_state(self, state):
    self.size = st.size
    self.irq_table_address = state.irq_table_address
    self.int_table_address = state.int_table_address

    for segment_state in state.mm_segment_states:
      self.__segments[segment_state.index] = True

    for page_state in state.mm_page_states:
      page = self.get_page(page_state.index)
      page.load_state(page_state)

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
    debug('mc.alloc_page: segment=%s' % SEGM_FMT(segment.u8) if segment else '')

    with self.lock:
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

  def free_page(self, page):
    debug('mc.free_page: page=%i, base=%s, segment=%s' % (page.index, ADDR_FMT(page.base_address), ADDR_FMT(page.segment_address)))

    with self.lock:
      del self.__pages[page.index]

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

    # IRQ table
    self.get_page(addr_to_page(self.irq_table_address)).read = True

    # INT table
    self.get_page(addr_to_page(self.int_table_address)).read = True

  def update_area_flags(self, address, size, flag, value):
    debug('mc.update_area_flags: address=%s, size=%s, flag=%s, value=%i' % (ADDR_FMT(address), SIZE_FMT(size), flag, value))

    self.for_each_page_in_area(address, size, lambda page_index, area_index: setattr(self.get_page(page_index), flag, value))

  def update_pages_flags(self, pages_start, pages_cnt, flag, value):
    debug('mc.update_pages_flags: page=%s, cnt=%s, flag=%s, value=%i' % (PAGE_FMT(pages_start), SIZE_FMT(pages_cnt), flag, value))

    self.for_each_page(pages_start, pages_cnt, lambda page_index, area_index: setattr(self.get_page(page_index), flag, value))

  def reset_area_flags(self, address, size):
    debug('mc.reset_area_flags: address=%s, size=%s' % (ADDR_FMT(address), SIZE_FMT(size)))

    self.for_each_page_in_area(address, size, lambda page_index, area_index: self.get_page(page_index).flags_reset())

  def reset_pages_flags(self, pages_start, pages_cnt):
    debug('mc.reset_pages_flags: page=%s, size=%s' % (PAGE_FMT(pages_start), SIZE_FMT(pages_cnt)))

    self.for_each_page(pages_start, pages_cnt, lambda page_index, area_index: self.get_page(page_index).flags_reset())

  def __load_content_u8(self, segment, base, content):
    bsp  = UInt24(segment_addr_to_addr(segment.u8, base.u16))
    sp   = UInt24(bsp.u24)
    size = UInt16(len(content))

    debug('mc.__load_content_u8: segment=%s, base=%s, size=%s, sp=%s' % (SEGM_FMT(segment.u8), ADDR_FMT(base.u16), SIZE_FMT(size.u16), ADDR_FMT(sp.u24)))

    for i in content:
      self.write_u8(sp.u24, i.u8, privileged = True)
      sp.u24 += 1

  def __load_content_u16(self, segment, base, content):
    bsp  = UInt24(segment_addr_to_addr(segment.u8, base.u16))
    sp   = UInt24(bsp.u24)
    size = UInt16(len(content) * 2)

    debug('mc.__load_content_u16: segment=%s, base=%s, size=%s, sp=%s' % (SEGM_FMT(segment.u8), ADDR_FMT(base.u16), SIZE_FMT(size.u16), ADDR_FMT(sp.u24)))

    for i in content:
      self.write_u16(sp.u24, i.u16, privileged = True)
      sp.u24 += 2

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

  def load_text(self, segment, base, content):
    self.__load_content_u32(segment, base, content)

  def load_data(self, segment, base, content):
    self.__load_content_u8(segment, base, content)

  def load_raw_sections(self, sections, csr = None, dsr = None, stack = True):
    debug('mc.load_raw_sections: csr=%s, dsr=%s, stack=%s' % (csr, dsr, stack))

    import mm.binary

    csr = csr or UInt8(self.alloc_segment().u8)
    dsr = dsr or UInt8(csr.u8)
    sp  = None
    ip  = None

    symbols = {}

    for s_name, section in sections.items():
      s_base_addr = None

      if section.type == mm.binary.SectionTypes.TEXT:
        s_base_addr = UInt24(segment_addr_to_addr(csr.u8, section.base.u16))

        self.load_text(csr, section.base, section.content)

      elif section.type == mm.binary.SectionTypes.DATA:
        s_base_addr = UInt24(segment_addr_to_addr(dsr.u8, section.base.u16))

        if 'b' not in section.flags:
          self.load_data(dsr, section.base, section.content)

      elif section.type == mm.binary.SectionTypes.SYMBOLS:
        for symbol in section.content:
          symbols[symbol.name] = symbol.section_ptr

        if not ip:
          ip = get_code_entry_address(section, section.content)

      if s_base_addr:
        self.reset_area_flags(s_base_addr.u24, len(section))
        self.update_area_flags(s_base_addr.u24, len(section), 'read', True if 'r' in section.flags else False)
        self.update_area_flags(s_base_addr.u24, len(section), 'write', True if 'w' in section.flags else False)
        self.update_area_flags(s_base_addr.u24, len(section), 'execute', True if 'x' in section.flags else False)

    if stack:
      stack_page = self.get_page(self.alloc_page(dsr))
      stack_page.read = True
      stack_page.write = True
      sp = UInt16(stack_page.segment_address + PAGE_SIZE)

    return (csr, dsr, sp, ip, symbols)

  def load_file(self, file_in, csr = None, dsr = None, stack = True):
    debug('mc.load_file: file_in=%s, csr=%s, dsr=%s' % (file_in, csr, dsr))

    import mm.binary

    # One segment for code and data
    csr = csr or UInt8(self.alloc_segment().u8)
    dsr = dsr or UInt8(csr.u8)
    sp  = None
    ip  = None

    symbols = {}

    with mm.binary.File(file_in, 'r') as f_in:
      f_in.load()

      f_header = f_in.get_header()

      for i in range(0, f_header.sections):
        s_header, s_content = f_in.get_section(i)

        s_base_addr = None

        if s_header.type == mm.binary.SectionTypes.TEXT:
          s_base_addr = UInt24(segment_addr_to_addr(csr.u8, s_header.base))

          self.load_text(csr, UInt16(s_header.base), s_content)

        elif s_header.type == mm.binary.SectionTypes.DATA:
          s_base_addr = UInt24(segment_addr_to_addr(dsr.u8, s_header.base))

          if s_header.flags.bss != 1:
            self.load_data(dsr, UInt16(s_header.base), s_content)

        elif s_header.type == mm.binary.SectionTypes.SYMBOLS:
          for symbol in s_content:
            symbols[symbol.get_name()] = UInt16(symbol.address)

          if not ip:
            ip = get_code_entry_address(s_header, s_content)

        if s_base_addr:
          self.reset_area_flags(s_base_addr.u24, s_header.size)
          self.update_area_flags(s_base_addr.u24, s_header.size, 'read', True if s_header.flags.readable == 1 else False)
          self.update_area_flags(s_base_addr.u24, s_header.size, 'write', True if s_header.flags.writable == 1 else False)
          self.update_area_flags(s_base_addr.u24, s_header.size, 'execute', True if s_header.flags.executable == 1 else False)

    if stack:
      stack_page = self.get_page(self.alloc_page(dsr))
      stack_page.read = True
      stack_page.write = True
      sp = UInt16(stack_page.segment_address + PAGE_SIZE)

    return (csr, dsr, sp, ip, symbols)

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

    mmap_flags = mmap.MAP_SHARED if shared else mmap.MAP_PRIVATE

    mmap_prot = 0
    if access.flags.read:
      mmap_prot |= mmap.PROT_READ
    if access.flags.write:
      mmap_prot |= mmap.PROT_WRITE

    ptr = mmap.mmap(
      self.__get_mmap_fileno(file_path),
      size,
      flags = mmap_flags,
      prot = mmap_prot,
      offset = offset)

    def __create_mmap_page(page_index, area_index):
      self.__pages[page_index] = MMapMemoryPage(self, page_index, ptr, area_index * PAGE_SIZE)

    self.for_each_page(pages_start, pages_cnt, __create_mmap_page)

    self.reset_pages_flags(pages_start, pages_cnt)

    if access.flags.read:
      self.update_pages_flags(pages_start, pages_cnt, 'read', 1)
    if access.flags.write:
      self.update_pages_flags(pages_start, pages_cnt, 'write', 1)

    return MMapArea(address, size, file_path, ptr, pages_start, pages_cnt)

  def unmmap_area(self, mmap_area):
    self.reset_pages_flags(mmap_area.pages_start, mmap_area.pages_cnt)

    def __remove_mmap_page(page_index, _):
      del self.__pages[page_index]

    self.for_each_page(mmap_area.pages_start, mmap_area.pages_cnt, __remove_mmap_page)

    del self.mmap_areas[mmap_area.address]

    mmap_area.ptr.close()

    self.__put_mmap_fileno(mmap_area.file_path)

  def cas_u16(self, addr, test, rep):
    page = self.get_page(addr_to_page(addr))

    with page.lock:
      v = page.read_u16(addr_to_offset(addr))
      if v.u16 == test.u16:
        v.u16 = rep.u16
        return True
      return v

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

  def read_block(self, addr, size, privileged = False):
    debug('mc.read_block: addr=%s, size=%s, privileged=%s' % (ADDR_FMT(addr), UINT16_FMT(size), privileged))

    if size % 32 != 0:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    return self.get_page(addr_to_page(addr)).read_block(addr_to_offset(addr), 32)

  def write_block(self, addr, size, buff, privileged = False):
    debug('mc.write_block: addr=%s, size=%s, privileged=%s' % (ADDR_FMT(addr), UINT16_FMT(size), privileged))

    if size % 32 != 0:
      raise AccessViolationError('Unable to access unaligned address: addr=%s' % ADDR_FMT(addr))

    self.get_page(addr_to_page(addr)).write_block(addr_to_offset(addr), size, buff)

  def save_interrupt_vector(self, table, index, desc):
    from cpu import InterruptVector

    debug('mc.save_interrupt_vector: table=%s, index=%i, desc=(CS=%s, DS=%s, IP=%s)'
      % (ADDR_FMT(table), index, UINT8_FMT(desc.cs), UINT8_FMT(desc.ds), UINT16_FMT(desc.ip)))

    vector_address = UInt24(table + index * sizeof(InterruptVector)).u24

    self.write_u8( vector_address,     desc.cs, privileged = True)
    self.write_u8( vector_address + 1, desc.ds, privileged = True)
    self.write_u16(vector_address + 2, desc.ip, privileged = True)

  def load_interrupt_vector(self, table, index):
    from cpu import InterruptVector

    debug('mc.load_interrupt_vector: table=%s, index=%i' % (ADDR_FMT(table.u24), index))

    desc = InterruptVector()

    vector_address = UInt24(table.u24 + index * sizeof(InterruptVector)).u24

    desc.cs = self.read_u8( vector_address,     privileged = True).u8
    desc.ds = self.read_u8( vector_address + 1, privileged = True).u8
    desc.ip = self.read_u16(vector_address + 2, privileged = True).u16

    return desc
