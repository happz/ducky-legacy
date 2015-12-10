import mmap

from six import iteritems, iterkeys, itervalues, PY2
from six.moves import range

from ctypes import LittleEndianStructure, c_ubyte, c_ushort, c_uint

from ..interfaces import ISnapshotable
from ..errors import AccessViolationError, InvalidResourceError
from ..util import align, sizeof_fmt, Flags
from ..snapshot import SnapshotNode

import enum

# Types
from ctypes import c_byte as i8  # NOQA
from ctypes import c_short as i16  # NOQA
from ctypes import c_int as i32  # NOQA

from ctypes import c_ubyte as u8  # NOQA
from ctypes import c_ushort as u16  # NOQA
from ctypes import c_uint as u32  # NOQA

PAGE_SHIFT = 8
#: Size of memory page, in bytes.
PAGE_SIZE = (1 << PAGE_SHIFT)
PAGE_MASK = (~(PAGE_SIZE - 1))

SEGMENT_SHIFT = 16
#: Size of segment, in pages
SEGMENT_SIZE  = 256  # pages
SEGMENT_PROTECTED = 0  # first segment is already allocated

class MMOperationList(enum.IntEnum):
  ALLOC    = 3
  FREE     = 4
  UNUSED   = 5
  MMAP     = 6
  UNMMAP   = 7

MM_FLAG_READ    = 0x0001
MM_FLAG_WRITE   = 0x0002
MM_FLAG_EXECUTE = 0x0004
MM_FLAG_DIRTY   = 0x0008

MM_FLAG_CS      = 0x1000

from ..util import UINT8_FMT, UINT16_FMT, UINT24_FMT, UINT32_FMT, ADDR_FMT  # noqa

def SEGM_FMT(segment):
  return UINT8_FMT(segment)

def SIZE_FMT(size):
  return str(size)

def OFFSET_FMT(offset):
  s = '-' if offset < 0 else ''

  return '{}0x{:04X}'.format(s, abs(offset))

class MalformedBinaryError(Exception):
  pass

class UInt8(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u8', c_ubyte)
  ]

  def __repr__(self):
    return '<(u8) 0x{:02X}>'.format(self.u8)

class UInt16(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u16', c_ushort)
  ]

  def __repr__(self):
    return '<(u16) 0x{:04X}>'.format(self.u16)

# Yes, this one is larger but it's used only for transporting
# addresses between CPUs and memory controller => segment
# register and u16 have to fit in.
class UInt24(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u24', c_uint, 24)
  ]

  def __repr__(self):
    return '<(u24) 0x{:06X}>'.format(self.u24)

class UInt32(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('u32', c_uint)
  ]

  def __repr__(self):
    return '<(u32) 0x{:06X}>'.format(self.u32)

def segment_base_addr(segment):
  return segment * SEGMENT_SIZE * PAGE_SIZE

def segment_addr_to_addr(segment, addr):
  return segment * SEGMENT_SIZE * PAGE_SIZE + addr

def addr_to_segment(addr):
  return (addr & 0xFF0000) >> 16

def addr_to_page(addr):
  return (addr & PAGE_MASK) >> PAGE_SHIFT

def addr_to_offset(addr):
  return addr & (PAGE_SIZE - 1)

def area_to_pages(addr, size):
  return ((addr & PAGE_MASK) >> PAGE_SHIFT, align(PAGE_SIZE, size) // PAGE_SIZE)

class PageTableEntry(Flags):
  _fields_ = [
    ('read',    c_ubyte, 1),
    ('write',   c_ubyte, 1),
    ('execute', c_ubyte, 1),
    ('dirty',   c_ubyte, 1),
    ('stack',   c_ubyte, 1),
    ('cache',   c_ubyte, 1)
  ]

  flag_labels = 'RWXDSC'

  @staticmethod
  def default():
    return PageTableEntry.create(cache = True)

class MemoryPageState(SnapshotNode):
  def __init__(self, *args, **kwargs):
    super(MemoryPageState, self).__init__('index', 'content')

class MemoryPage(object):
  """
  Base class for all memory pages of any kinds.

  Memory page has a set of boolean flags that determine access to and behavior
  of the page.

  +-------------+-----------------------------------------------------------------------------+-----------+
  | Flag        | Meaning                                                                     | Default   |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``read``    | page is readable by executed instructions                                   | ``False`` |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``write``   | page is writable by executed instructions                                   | ``False`` |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``execute`` | content of the page can be used as executable instructions                  | ``False`` |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``dirty``   | there have been write access to this page, its content has changed          | ``False`` |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``stack``   | page is a stack                                                             | ``False`` |
  +-------------+-----------------------------------------------------------------------------+-----------+
  | ``cache``   | all RW accesses to this page made by CPU cores go through their data caches | ``True``  |
  +-------------+-----------------------------------------------------------------------------+-----------+

  :param ducky.mm.MemoryController controller: Controller that owns this page.
  :param int index: Serial number of this page.
  """

  def __init__(self, controller, index):
    super(MemoryPage, self).__init__()

    self.controller = controller
    self.index = index

    self.DEBUG = self.controller.DEBUG
    self.INFO = self.controller.INFO
    self.WARN = self.controller.WARN
    self.ERROR = self.controller.ERROR
    self.EXCEPTION = self.controller.EXCEPTION

    self.base_address = self.index * PAGE_SIZE
    self.segment_address = self.base_address % (SEGMENT_SIZE * PAGE_SIZE)

  def __repr__(self):
    return '<%s index=%i, base=%s, segment_addr=%s>' % (self.__class__.__name__, self.index, ADDR_FMT(self.base_address), ADDR_FMT(self.segment_address))

  def save_state(self, parent):
    """
    Create state of this page, and attach it to snapshot tree.

    :param parent: Parent snapshot node.
    :type parent: ducky.snapshot.SnapshotNode
    """

    state = parent.add_child('page_{}'.format(self.index), MemoryPageState())

    state.index = self.index
    state.content = [ord(i) if isinstance(i, str) else i for i in self.data]

    return state

  def load_state(self, state):
    """
    Restore page from a snapshot.
    """

    for i in range(0, PAGE_SIZE):
      self.data[i] = state.content[i]

  def __len__(self):
    """
    :return: length of this page. By default, all pages have the same length.
    :rtype: int
    """

    return PAGE_SIZE

  def clear(self):
    """
    Clear page.

    This operation is implemented by child classes.
    """

    raise NotImplementedError('Not allowed to clear memory on this address: page={}'.format(self.index))

  def read_u8(self, offset):
    """
    Read byte.

    This operation is implemented by child classes.

    :param int offset: offset of requested byte.
    :rtype: int
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

  def read_u16(self, offset):
    """
    Read word.

    This operation is implemented by child classes.

    :param int offset: offset of requested word.
    :rtype: int
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

  def read_u32(self, offset):
    """
    Read longword.

    This operation is implemented by child classes.

    :param int offset: offset of requested longword.
    :rtype: int
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

  def write_u8(self, offset, value):
    """
    Write byte.

    This operation is implemented by child classes.

    :param int offset: offset of requested byte.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

  def write_u16(self, offset, value):
    """
    Write word.

    This operation is implemented by child classes.

    :param int offset: offset of requested word.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

  def write_u32(self, offset, value):
    """
    Write longword.

    This operation is implemented by child classes.

    :param int offset: offset of requested longword.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page=%s, offset={}'.format(self.index, offset))

class AnonymousMemoryPage(MemoryPage):
  """
  "Anonymous" memory page - this page is just a plain array of bytes, and is
  not backed by any storage. Its content lives only in the memory.

  Page is created with all bytes set to zero.
  """

  def __init__(self, controller, index):
    super(AnonymousMemoryPage, self).__init__(controller, index)

    self.data = bytearray([0 for _ in range(0, PAGE_SIZE)])

  def clear(self):
    self.DEBUG('%s.clear', self.__class__.__name__)

    for i in range(0, PAGE_SIZE):
      self.data[i] = 0

  def read_u8(self, offset):
    self.DEBUG('%s.read_u8: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.data[offset]

  def read_u16(self, offset):
    self.DEBUG('%s.read_u16: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.data[offset] | (self.data[offset + 1] << 8)

  def read_u32(self, offset):
    self.DEBUG('%s.do_read_u32: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.data[offset] | (self.data[offset + 1] << 8) | (self.data[offset + 2] << 16) | (self.data[offset + 3] << 24)

  def write_u8(self, offset, value):
    self.DEBUG('%s.do_write_u8: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.data[offset] = value

  def write_u16(self, offset, value):
    self.DEBUG('%s.write_u16: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.data[offset]     =  value & 0x00FF
    self.data[offset + 1] = (value & 0xFF00) >> 8

  def write_u32(self, offset, value):
    self.DEBUG('%s.write_u32: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.data[offset]     =  value &       0xFF
    self.data[offset + 1] = (value &     0xFF00) >> 8
    self.data[offset + 2] = (value &   0xFF0000) >> 16
    self.data[offset + 3] = (value & 0xFF000000) >> 24

class ExternalMemoryPage(MemoryPage):
  """
  Memory page backed by an external source. Source is an array of bytes,
  and can be provided by device driver, mmaped file, or by any other mean.
  """

  def __init__(self, controller, index, data, offset = 0):
    super(ExternalMemoryPage, self).__init__(controller, index)

    self.data = data
    self.offset = offset

  def __repr__(self):
    return '<%s index=%i, base=%s, segment_addr=%s, offset=%s>' % (self.__class__.__name__, self.index, ADDR_FMT(self.base_address), ADDR_FMT(self.segment_address), ADDR_FMT(self.offset))

  def save_state(self, parent):
    state = super(ExternalMemoryPage, self).save_state(parent)

    state.content = [ord(i) if isinstance(i, str) else i for i in self.data[self.offset:self.offset + PAGE_SIZE]]

  def clear(self):
    self.DEBUG('%s.clear', self.__class__.__name__)

    for i in range(0, PAGE_SIZE):
      self.data[i] = 0

  def get(self, offset):
    """
    Get one byte from page. Override this method in case you need a different
    offset of requested byte.

    :param int offset: offset of the requested byte.
    :rtype: int
    :returns: byte at position in page.
    """

    return self.data[self.offset + offset]

  def put(self, offset, b):
    """
    Put one byte into page. Override this method in case you need a different
    offset of requested byte.

    :param int offset: offset of modified byte.
    :param int b: new value.
    """

    self.data[self.offset + offset] = b

  def read_u8(self, offset):
    self.DEBUG('%s.read_u8: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.get(offset)

  def read_u16(self, offset):
    self.DEBUG('%s.read_u16: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.get(offset) | (self.get(offset + 1) << 8)

  def read_u32(self, offset):
    self.DEBUG('%s.read_u32: page=%s, offset=%s', self.__class__.__name__, self.index, offset)

    return self.get(offset) | (self.get(offset + 1) << 8) | (self.get(offset + 2) << 16) | (self.get(offset + 3) << 24)

  def write_u8(self, offset, value):
    self.DEBUG('%s.write_u8: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.put(offset, value)

  def write_u16(self, offset, value):
    self.DEBUG('%s.write_u16: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.put(offset, value & 0x00FF)
    self.put(offset + 1, (value & 0xFF00) >> 8)

  def write_u32(self, offset, value):
    self.DEBUG('%s.write_u32: page=%s, offset=%s, value=%s', self.__class__.__name__, self.index, offset, value)

    self.put(offset, value & 0x00FF)
    self.put(offset + 1, (value & 0xFF00) >> 8)
    self.put(offset + 2, (value & 0xFF0000) >> 16)
    self.put(offset + 3, (value & 0xFF000000) >> 24)

class MMapMemoryPage(ExternalMemoryPage):
  """
  Memory page backed by an external file that is accessible via ``mmap()``
  call. It's a part of one of mm.MMapArea instances, and if such area was
  opened as `shared`, every change in this page content will affect the
  content of external file, and vice versa, every change of external file
  will be reflected in content of this page (if this page lies in affected
  area).
  """

  def __init__(self, area, *args, **kwargs):
    super(MMapMemoryPage, self).__init__(*args, **kwargs)

    self.area = area

    if PY2:
      self.get, self.put = self._get_py2, self._put_py2

    else:
      self.get, self.put = self._get_py3, self._put_py3

  def _get_py2(self, offset):
    return ord(self.data[self.offset + offset])

  def _put_py2(self, offset, b):
    self.data[self.offset + offset] = chr(b)

  def _get_py3(self, offset):
    return self.data[self.offset + offset]

  def _put_py3(self, offset, b):
    self.data[self.offset + offset] = b

class MMapAreaState(SnapshotNode):
  def __init__(self):
    super(MMapAreaState, self).__init__('address', 'size', 'path', 'offset', 'fd')

class MMapArea(object):
  def __init__(self, ptr, address, size, filepath, fd, offset, pages_start, pages_cnt, flags):
    super(MMapArea, self).__init__()

    self.ptr = ptr
    self.address = address
    self.size = size
    self.filepath = filepath
    self.fd = fd
    self.offset = offset
    self.pages_start = pages_start
    self.pages_cnt = pages_cnt
    self.flags = flags

  def __repr__(self):
    return '<MMapArea: address=%s, size=%s, filepath=%s, fd=%s, pages-start=%s, pages-cnt=%i, flags=%s>' % (ADDR_FMT(self.address), self.size, self.filepath, self.fd, self.pages_start, self.pages_cnt, self.flags.to_string())

  def save_state(self, parent):
    pass

  def load_state(self, state):
    pass

class MemoryRegionState(SnapshotNode):
  def __init__(self):
    super(MemoryRegionState, self).__init__('name', 'address', 'size', 'flags', 'pages_start', 'pages_cnt')

class MemoryRegion(ISnapshotable, object):
  region_id = 0

  def __init__(self, mc, name, address, size, flags):
    super(MemoryRegion, self).__init__()

    self.memory = mc

    self.id = MemoryRegion.region_id
    MemoryRegion.region_id += 1

    self.name = name
    self.address = address
    self.size = size
    self.flags = flags

    self.pages_start, self.pages_cnt = area_to_pages(self.address, self.size)

    self.memory.machine.DEBUG('MemoryRegion: name=%s, address=%s, size=%s, flags=%s, pages_start=%s, pages_cnt=%s', name, address, size, self.flags.to_string(), self.pages_start, self.pages_cnt)

  def __repr__(self):
    return '<MemoryRegion: name=%s, address=%s, size=%s, flags=%s, pages_start=%s, pages_cnt=%s' % (self.name, self.address, self.size, self.flags.to_string(), self.pages_start, self.pages_cnt)

  def save_state(self, parent):
    state = parent.add_child('memory_region_{}'.format(self.id), MemoryRegionState())

    state.name = self.name
    state.address = self.address
    state.size = self.size
    state.flags = self.flags.to_uint16()
    state.pages_start = self.pages_start
    state.pages_cnt = self.pages_cnt

  def load_state(self, state):
    pass

class MemoryState(SnapshotNode):
  def __init__(self):
    super(MemoryState, self).__init__('size', 'segments')

  def get_page_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('page_')]

class MemoryController(object):
  """
  Memory controller handles all operations regarding main memory.

  :param ducky.machine.Machine machine: virtual machine that owns this controller.
  :param int size: size of memory, in bytes.
  :raises ducky.errors.InvalidResourceError: when memory size is not multiple of
    :py:data:`ducky.mm.PAGE_SIZE`, or when size is not multiply of
    :py:data:`ducky.mm.SEGMENT_SIZE` pages.
  """

  def __init__(self, machine, size = 0x1000000):
    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if size % (SEGMENT_SIZE * PAGE_SIZE) != 0:
      raise InvalidResourceError('Memory size must be multiple of SEGMENT_SIZE')

    self.machine = machine

    # Setup logging - create our local shortcuts to machine' logger
    self.DEBUG = self.machine.DEBUG
    self.INFO = self.machine.INFO
    self.WARN = self.machine.WARN
    self.ERROR = self.machine.ERROR
    self.EXCEPTION = self.machine.EXCEPTION

    self.force_aligned_access = self.machine.config.getbool('memory', 'force-aligned-access', default = False)

    self.size = size
    self.__pages_cnt = size // PAGE_SIZE
    self.__pages = {}

    self.__segments_cnt = size // (SEGMENT_SIZE * PAGE_SIZE)
    self.__segments = {}

    # mmap
    self.opened_mmap_files = {}  # path: (cnt, file)
    self.mmap_areas = {}

  def save_state(self, parent):
    self.DEBUG('mc.save_state')

    state = parent.add_child('memory', MemoryState())

    state.size = self.size

    state.segments = []
    for segment in iterkeys(self.__segments):
      state.segments.append(segment)

    for page in itervalues(self.__pages):
      page.save_state(state)

  def load_state(self, state):
    self.size = state.size

    for segment in state.segments:
      self.__segments[segment] = True

    for page_state in state.get_children():
      page = self.page(page_state.index)
      page.load_state(page_state)

  def alloc_segment(self):
    """
    Reserve one of free memory segments.

    :returns: index of reserved segment.
    :rtype: int
    :raises ducky.errors.InvalidResourceError: when there are no free segments.
    """

    self.DEBUG('mc.alloc_segment')

    for i in range(0, self.__segments_cnt):
      if i in self.__segments:
        continue

      # No SegmentMapEntry flags are in use right now, just keep this option open
      self.DEBUG('mc.alloc_segment: segment=%s', i)

      self.__segments[i] = True
      return i

    raise InvalidResourceError('No free segment available')

  def alloc_specific_segment(self, segment):
    self.DEBUG('mc.alloc_specific_segment: segment=%s', UINT8_FMT(segment))

    if segment in self.__segments:
      raise InvalidResourceError('Requested segment not available: segment=%s' % UINT8_FMT(segment))

    self.__segments[segment] = True

    return segment

  def __set_page(self, pg):
    """
    Install page object for a specific memory page.

    :param ducky.mm.MemoryPage pg: page to be installed
    :returns: installed page
    :rtype: :py:class:`ducky.mm.MemoryPage`
    """

    assert pg.index not in self.__pages

    self.__pages[pg.index] = pg
    return pg

  def __remove_page(self, pg):
    """
    Removes page object for a specific memory page.

    :param ducky.mm.MemoryPage pg: page to be removed
    """

    assert pg.index in self.__pages

    del self.__pages[pg.index]

  def __alloc_page(self, index):
    """
    Allocate new anonymous page for usage. The first available index is used.

    Be aware that this method does NOT check if page is already allocated. If
    it is, it is just overwritten by new anonymous page.

    :param int index: index of requested page.
    :returns: newly reserved page.
    :rtype: :py:class:`ducky.mm.AnonymousMemoryPage`
    """

    return self.__set_page(AnonymousMemoryPage(self, index))

  def alloc_specific_page(self, index):
    """
    Allocate new anonymous page with specific index for usage.

    :param int index: allocate page with this particular index.
    :returns: newly reserved page.
    :rtype: :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.AccessViolationError: when page is already allocated.
    """

    self.DEBUG('mc.alloc_specific_page: index=%s', index)

    if index in self.__pages:
      raise AccessViolationError('Page {} is already allocated'.format(index))

    return self.__alloc_page(index)

  def alloc_pages(self, segment = None, count = 1):
    """
    Allocate continuous sequence of anonymous pages.

    :param int segment: if not ``None``, allocated pages will be from this
      segment.
    :param int count: number of requested pages.
    :returns: list of newly allocated pages.
    :rtype: ``list`` of :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.InvalidResourceError: when there is no available sequence of
      pages.
    """

    self.DEBUG('mc.alloc_pages: segment=%s, count=%s', segment if segment else '', count)

    if segment is not None:
      pages_start = segment * SEGMENT_SIZE
      pages_cnt = SEGMENT_SIZE
    else:
      pages_start = 0
      pages_cnt = self.__pages_cnt

    self.DEBUG('mc.alloc_pages: page=%s, cnt=%s', pages_start, pages_cnt)

    for i in range(pages_start, pages_start + pages_cnt):
      for j in range(i, i + count):
        if j in self.__pages:
          break

      else:
        return [self.__alloc_page(j) for j in range(i, i + count)]

    raise InvalidResourceError('No sequence of free pages available')

  def alloc_page(self, segment = None):
    """
    Allocate new anonymous page for usage. The first available index is used.

    :param int segment: if not ``None``, allocated page will be from this
      segment.
    :returns: newly reserved page.
    :rtype: :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.InvalidResourceError: when there is no available page.
    """

    self.DEBUG('mc.alloc_page: segment=%s', segment if segment else '')

    if segment is not None:
      pages_start = segment * SEGMENT_SIZE
      pages_cnt = SEGMENT_SIZE
    else:
      pages_start = 0
      pages_cnt = self.__pages_cnt

    self.DEBUG('mc.alloc_page: page=%s, cnt=%s', pages_start, pages_cnt)

    for i in range(pages_start, pages_start + pages_cnt):
      if i not in self.__pages:
        self.DEBUG('mc.alloc_page: page=%s', i)
        return self.__alloc_page(i)

    raise InvalidResourceError('No free page available')

  def register_page(self, pg):
    """
    Install page object for a specific memory page. This method is intended
    for external objects, e.g. device drivers to install their memory page
    objects to handle memory-mapped IO.

    :param ducky.mm.MemoryPage pg: page to be installed
    :returns: installed page
    :rtype: :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.AccessViolationError: when there is already allocated page
    """

    self.DEBUG('mc.register_page: pg=%s', pg)

    if pg.index in self.__pages:
      raise AccessViolationError('Page {} is already allocated'.format(pg.index))

    return self.__set_page(pg)

  def unregister_page(self, pg):
    """
    Remove page object for a specific memory page. This method is intende
    for external objects, e.g. device drivers to remove their memory page objects
    handling memory-mapped IO.

    :param ducky.mm.MemoryPage pg: page to be removed
    :raises ducky.errors.AccessViolationError: when there is no allocated page
    """

    self.DEBUG('mc.unregister_page: pg=%s', pg)

    if pg.index not in self.__pages:
      raise AccessViolationError('Page {} is not allocated'.format(pg.index))

    self.__remove_page(pg)

  def alloc_stack(self, segment = None):
    """
    Allocate page for a stack. Such page does not differ from other but this
    pages are requested from different places of virtual machine, therefore
    this shortcut method.

    :param int segment: if not ``None``, , allocated page will be from this
      segment.
    :returns: newly allocated page, and base address of the next memory page.
      This address is in fact a stack pointer for storing the first value on
      newly allocated stack (`decrement and store`).
    :rtype: (:py:class:`ducky.mm.AnonymousMemoryPage`, ``int``)
    :raises ducky.errors.InvalidResourceError: when there is no available page.
    """

    pg = self.alloc_page(segment)

    return (pg, pg.segment_address + PAGE_SIZE)

  def free_page(self, page):
    """
    Free memory page when it's no longer needed.

    :param ducky.mm.MemoryPage page: page to be freed.
    """

    self.DEBUG('mc.free_page: page=%i, base=%s, segment=%s', page.index, page.base_address, page.segment_address)

    self.__remove_page(page)

  def free_pages(self, page, count = 1):
    """
    Free a continuous sequence of pages when they are no longer needed.

    :param ducky.mm.MemoryPage page: first page in series.
    :param int count: number of pages.
    """

    self.DEBUG('mc.free_pages: page=%i, base=%s, segment=%s, count=%s', page.index, page.base_address, page.segment_address, count)

    for i in range(page.index, page.index + count):
      self.free_page(self.__pages[i])

  def page(self, index):
    """
    Return memory page, specified by its index from the beginning of memory.

    :param int index: index of requested page.
    :rtype: :py:class:`ducky.mm.MemoryPage`
    :raises ducky.errors.AccessViolationError: when requested page is not allocated.
    """

    if index not in self.__pages:
      raise AccessViolationError('Page {} not allocated yet'.format(index))

    return self.__pages[index]

  def pages(self, pages_start = 0, pages_cnt = None, ignore_missing = False):
    """
    Return list of memory pages.

    :param int pages_start: index of the first page, 0 by default.
    :param int pages_cnt: number of pages to get, number of all memory pages by default.
    :param bool ignore_missing: if ``True``, ignore missing pages, ``False`` by default.
    :raises ducky.errors.AccessViolationError: when ``ignore_missing == False`` and there's
      a missing page in requested range, this exception is rised.
    :returns: list of pages in area
    :rtype: `list` of :py:class:`ducky.mm.MemoryPage`
    """

    self.DEBUG('mc.pages: pages_start=%s, pages_cnt=%s, ignore_missing=%s', pages_start, pages_cnt, ignore_missing)

    pages_cnt = pages_cnt or self.__pages_cnt

    if ignore_missing is True:
      return (self.__pages[i] for i in range(pages_start, pages_start + pages_cnt) if i in self.__pages)
    else:
      return (self.__pages[i] for i in range(pages_start, pages_start + pages_cnt))

  def pages_in_area(self, address = 0, size = None, ignore_missing = False):
    """
    Return list of memory pages.

    :param u24 address: beggining address of the area, by default 0.
    :param u24 size: size of the area, by default the whole memory size.
    :param bool ignore_missing: if ``True``, ignore missing pages, ``False`` by default.
    :raises ducky.errors.AccessViolationError: when ``ignore_missing == False`` and there's
      a missing page in requested range, this exception is rised.
    :returns: list of pages in area
    :rtype: `list` of :py:class:`ducky.mm.MemoryPage`
    """

    self.DEBUG('mc.pages_in_area: address=%s, size=%s', ADDR_FMT(address), size)

    size = size or self.size
    pages_start, pages_cnt = area_to_pages(address, size)

    return self.pages(pages_start = pages_start, pages_cnt = pages_cnt, ignore_missing = ignore_missing)

  def boot(self):
    """
    Prepare memory controller for immediate usage by other components.
    """

    self.INFO('mm: %s, %s available', sizeof_fmt(self.size, max_unit = 'Ki'), sizeof_fmt(self.size - len(self.__pages) * PAGE_SIZE, max_unit = 'Ki'))

  def halt(self):
    for area in list(self.mmap_areas.values()):
      self.unmmap_area(area)

  def __load_content_u8(self, segment, base, content):
    from ..cpu.assemble import SpaceSlot

    bsp  = segment_addr_to_addr(segment, base)
    sp   = bsp
    size = len(content)

    self.DEBUG('mc.__load_content_u8: segment=%s, base=%s, size=%s, sp=%s', UINT8_FMT(segment), UINT16_FMT(base), size, UINT16_FMT(sp))

    for i in content:
      if type(i) == SpaceSlot:
        sp += i.size.u16
      else:
        self.write_u8(sp, i.u8)
        sp += 1

  def __load_content_u16(self, segment, base, content):
    bsp  = segment_addr_to_addr(segment, base)
    sp   = bsp
    size = len(content) * 2

    self.DEBUG('mc.__load_content_u16: segment=%s, base=%s, size=%s, sp=%s', UINT8_FMT(segment), UINT16_FMT(base), size, UINT16_FMT(sp))

    for i in content:
      self.write_u16(sp, i.u16)
      sp += 2

  def __load_content_u32(self, segment, base, content):
    bsp = segment_addr_to_addr(segment, base)
    sp   = bsp
    size = len(content) * 4

    self.DEBUG('mc.__load_content_u32: segment=%s, base=%s, size=%s, sp=%s', UINT8_FMT(segment), UINT16_FMT(base), size, UINT16_FMT(sp))

    for i in content:
      self.write_u32(sp, i.u32)
      sp += 4

  def load_text(self, segment, base, content):
    self.DEBUG('mc.load_text: segment=%s, base=%s', UINT8_FMT(segment), UINT16_FMT(base))

    self.__load_content_u32(segment, base, content)

  def load_data(self, segment, base, content):
    self.DEBUG('mc.load_data: segment=%s, base=%s', UINT8_FMT(segment), UINT16_FMT(base))

    self.__load_content_u8(segment, base, content)

  def __set_section_flags(self, pages_start, pages_cnt, flags):
    self.DEBUG('__set_section_flags: start=%s, cnt=%s, flags=%s', pages_start, pages_cnt, flags)

    self.machine.set_pages_ptes(self.machine.pt_address, pages_start, pages_cnt, read = flags.readable == 1, write = flags.writable == 1, execute = flags.executable == 1)

  def create_binary_stack(self, segment, regions):
    from .binary import SectionFlags

    pg, sp = self.alloc_stack(segment = segment)
    regions.append(MemoryRegion(self, 'stack', pg.base_address, PAGE_SIZE, SectionFlags.create(readable = True, writable = True)))
    return sp

  def load_file(self, file_in, csr = None, dsr = None, stack = True):
    self.DEBUG('mc.load_file: file_in=%s, csr=%s, dsr=%s', file_in, csr, dsr)

    from . import binary

    # One segment for code and data
    csr = csr or self.alloc_segment()
    dsr = dsr or csr
    sp  = None
    ip  = None

    symbols = {}
    regions = []

    with binary.File.open(self.machine.LOGGER, file_in, 'r') as f_in:
      f_in.load()

      f_header = f_in.get_header()

      for i in range(0, f_header.sections):
        s_header, s_content = f_in.get_section(i)

        self.DEBUG('loading section %s', f_in.string_table.get_string(s_header.name))

        s_base_addr = None

        if s_header.type == binary.SectionTypes.SYMBOLS:
          for symbol in s_content:
            symbols[f_in.string_table.get_string(symbol.name)] = UInt16(symbol.address)

          continue

        if s_header.flags.loadable != 1:
          continue

        s_base_addr = segment_addr_to_addr(csr if s_header.type == binary.SectionTypes.TEXT else dsr, s_header.base)
        pages_start, pages_cnt = area_to_pages(s_base_addr, s_header.file_size)

        if f_header.flags.mmapable == 1:
          # Always mmap sections as RW, and disable W if section' flags requires that
          # Otherwise, when program asks Vm to enable W, any access would fail because
          # the underlying mmap area was not mmaped as writable

          if s_header.flags.bss == 1:
            self.mmap_area(address = s_base_addr, size = s_header.file_size, offset = s_header.offset, flags = s_header.flags, shared = False, empty = True)

          else:
            self.mmap_area(filepath = f_in.name, address = s_base_addr, size = s_header.file_size, offset = s_header.offset, flags = s_header.flags, shared = False)

        else:
          for i in range(pages_start, pages_start + pages_cnt):
            self.__alloc_page(i)

          if s_header.type == binary.SectionTypes.TEXT:
            self.load_text(csr, s_header.base, s_content)

          elif s_header.type == binary.SectionTypes.DATA:
            if s_header.flags.bss != 1:
              self.load_data(dsr, s_header.base, s_content)

        if self.machine.config.getbool('machine', 'setup-pte', True):
          self.__set_section_flags(pages_start, pages_cnt, s_header.flags)

        regions.append(MemoryRegion(self, f_in.string_table.get_string(s_header.name), s_base_addr, s_header.file_size, s_header.flags))

    if stack:
      sp = self.create_binary_stack(dsr, regions)

      if self.machine.config.getbool('machine', 'setup-pte', True):
        self.machine.set_pages_ptes(self.machine.pt_address, regions[-1].pages_start, regions[-1].pages_cnt, read = True, write = True, stack = True)

    return (csr, dsr, sp, ip, symbols, regions, f_in)

  def __get_mmap_fileno(self, filepath):
    if filepath not in self.opened_mmap_files:
      self.opened_mmap_files[filepath] = [0, open(filepath, 'r+b')]

    desc = self.opened_mmap_files[filepath]

    desc[0] += 1
    return desc[1].fileno()

  def __put_mmap_fileno(self, filepath):
    desc = self.opened_mmap_files[filepath]

    desc[0] -= 1
    if desc[0] > 0:
      return

    desc[1].close()
    del self.opened_mmap_files[filepath]

  def mmap_area(self, filepath = None, fd = None, address = None, size = None, offset = 0, flags = None, shared = False, empty = False):
    """
    Assign set of memory pages to mirror external file, mapped into memory.

    :param string filepath: path of external file, whose content new area
      should reflect.
    :param u24 address: address where new area should start.
    :param u24 size: length of area, in bytes.
    :param int offset: starting point of the area in mmaped file.
    :param ducky.mm.binary.SectionFlags flags: specifies required flags for mmaped
      pages.
    :param bool shared: if ``True``, content of external file is mmaped as
      shared, i.e. all changes are visible to all processes, not only to the
      current ducky virtual machine.
    :returns: newly created mmap area.
    :rtype: ducky.mm.MMapArea
    :raises ducky.errors.InvalidResourceError: when ``size`` is not multiply of
      :py:data:`ducky.mm.PAGE_SIZE`, or when ``address`` is not multiply of
      :py:data:`ducky.mm.PAGE_SIZE`, or when any of pages in the affected area
      is already allocated.
    """

    self.DEBUG('mc.mmap_area: file=%s, fd=%s, offset=%s, size=%s, address=%s, flags=%s, shared=%s', filepath, fd, offset, size, ADDR_FMT(address), flags.to_string(), shared)

    if address is None or size is None:
      raise InvalidResourceError('Size and address are required arguments')

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if address % PAGE_SIZE != 0:
      raise InvalidResourceError('MMap area address must be multiple of PAGE_SIZE')

    if fd is None:
      if empty is True:
        fd = -1

      else:
        if filepath is None:
          raise InvalidResourceError('Filepath or fd are required arguments')

        fd = self.__get_mmap_fileno(filepath)

    pages_start, pages_cnt = area_to_pages(address, size)

    for i in range(pages_start, pages_start + pages_cnt):
      if i in self.__pages:
        raise InvalidResourceError('MMap request overlaps with existing pages: page=%s, area=%s' % (self.__pages[i], self.__pages[i].area))

    mmap_flags = mmap.MAP_SHARED if shared else mmap.MAP_PRIVATE

    if empty is True:
      mmap_flags |= mmap.MAP_ANONYMOUS

    # Always mmap as writable - VM will force read-only access using
    # page flags. But since it is possible to change page flags
    # in run-time, and request write access to areas originaly
    # loaded as read-only, such write access would fail because
    # the underlying mmap area was mmaped as read-only only, and this
    # limitation is not possible to overcome.
    mmap_prot = mmap.PROT_READ | mmap.PROT_WRITE

    ptr = mmap.mmap(
      fd,
      size,
      flags = mmap_flags,
      prot = mmap_prot,
      offset = offset)

    area = MMapArea(ptr, address, size, filepath, fd, ptr, pages_start, pages_cnt, flags)

    for i in range(pages_start, pages_start + pages_cnt):
      self.register_page(MMapMemoryPage(area, self, i, ptr, offset = (i - pages_start) * PAGE_SIZE))

    self.mmap_areas[area.address] = area

    return area

  def unmmap_area(self, mmap_area):
    self.machine.cpu_cache_controller.release_area_references(self.page(mmap_area.pages_start).base_address, mmap_area.pages_cnt * PAGE_SIZE)

    for pg in self.pages(pages_start = mmap_area.pages_start, pages_cnt = mmap_area.pages_cnt):
      self.unregister_page(pg)

    del self.mmap_areas[mmap_area.address]

    mmap_area.ptr.close()

    if mmap_area.filepath is not None:
      self.__put_mmap_fileno(mmap_area.filepath)

  def read_u8(self, addr):
    self.DEBUG('mc.read_u8: addr=%s', ADDR_FMT(addr))

    return self.page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u8(addr & (PAGE_SIZE - 1))

  def read_u16(self, addr):
    self.DEBUG('mc.read_u16: addr=%s', ADDR_FMT(addr))

    return self.page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u16(addr & (PAGE_SIZE - 1))

  def read_u32(self, addr):
    self.DEBUG('mc.read_u32: addr=%s', ADDR_FMT(addr))

    return self.page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u32(addr & (PAGE_SIZE - 1))

  def write_u8(self, addr, value):
    self.DEBUG('mc.write_u8: addr=%s, value=%s', ADDR_FMT(addr), UINT8_FMT(value))

    self.page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u8(addr & (PAGE_SIZE - 1), value)

  def write_u16(self, addr, value):
    self.DEBUG('mc.write_u16: addr=%s, value=%s', ADDR_FMT(addr), UINT16_FMT(value))

    self.page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u16(addr & (PAGE_SIZE - 1), value)

  def write_u32(self, addr, value):
    self.DEBUG('mc.write_u32: addr=%s, value=%s', ADDR_FMT(addr), UINT32_FMT(value))

    self.page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u32(addr & (PAGE_SIZE - 1), value)

  def save_interrupt_vector(self, table, index, desc):
    """
    save_interrupt_vector(mm.UInt24, int, cpu.InterruptVector)
    """

    from ..cpu import InterruptVector

    self.DEBUG('mc.save_interrupt_vector: table=%s, index=%i, desc=%s', table, index, desc)

    vector_address = table + index * InterruptVector.SIZE

    self.write_u8(vector_address, desc.cs & 0xFF)
    self.write_u8(vector_address + 1, desc.ds & 0xFF)
    self.write_u16(vector_address + 2, desc.ip & 0xFFFF)
    self.write_u16(vector_address + 4, desc.sp & 0xFFFF)

from ..interfaces import IVirtualInterrupt
from ..devices import VIRTUAL_INTERRUPTS, IRQList

class MMInterrupt(IVirtualInterrupt):
  def op_mmap(self, core):
    from .binary import SectionFlags
    from ..cpu.registers import Registers

    core.REG(Registers.R00).value = 0xFFFF

    address = segment_addr_to_addr(core.REG(Registers.DS).value, core.REG(Registers.R01).value)
    size = core.REG(Registers.R02).value
    filepath_ptr = segment_addr_to_addr(core.REG(Registers.DS).value, core.REG(Registers.R03).value)
    offset = core.REG(Registers.R04).value
    flags = core.REG(Registers.R05).value

    filepath = []
    filepath_ptr = segment_addr_to_addr(core.REG(Registers.DS).value, core.REG(Registers.R03).value)

    while True:
      c = core.MEM_IN8(filepath_ptr)
      if c == 0:
        break

      filepath.append(chr(c))

    filepath = ''.join(filepath)

    flags = SectionFlags(readable = flags & MM_FLAG_READ, writable = flags & MM_FLAG_WRITE, executable = flags & MM_FLAG_EXECUTE)

    self.mmap_area(filepath, address, size, offset = offset, flags = flags)

    core.REG(Registers.R00).value = address

  def op_unmmap(self, core):
    from ..cpu.registers import Registers

    core.REG(Registers.R00).value = 0xFFFF

    address = segment_addr_to_addr(core.REG(Registers.DS).value, core.REG(Registers.R01).value)

    area = self.core.memory.mmap_areas.get(address)
    if area is None:
      raise AccessViolationError('Unmmap is not allowed for this area: address=%s' % ADDR_FMT(address))

    self.core.memory.unmmap_area(area)

    core.REG(Registers.R00).value = 0

  def run(self, core):
    from ..cpu import do_log_cpu_core_state
    from ..cpu.registers import Registers

    core.DEBUG('MMInterrupt: triggered')

    do_log_cpu_core_state(core, logger = core.DEBUG)

    op = core.REG(Registers.R00).value

    if op == MMOperationList.ALLOC:
      core.REG(Registers.R00).value = 0xFFFF

      pages_cnt = core.REG(Registers.R01).value
      segment = core.REG(Registers.DS).value

      core.DEBUG('alloc: pages_cnt=%s, segment=%s', pages_cnt, segment)

      pages = core.cpu.machine.memory.alloc_pages(segment = segment, count = pages_cnt)

      # for pg in pages:
      #   pg.flags_reset()

      core.REG(Registers.R00).value = pages[0].base_address & 0x00FFFF

      core.DEBUG('alloc: address=%s', ADDR_FMT(pages[0].base_address))
      for pg in pages:
        core.DEBUG('alloc: pg=%i', pg.index)

    elif op == MMOperationList.FREE:
      core.REG(Registers.R00).value = 0xFFFF

      address = segment_addr_to_addr(core.REG(Registers.DS).value, core.REG(Registers.R01).value)
      pages_start = addr_to_page(address)
      pages_cnt = core.REG(Registers.R02).value
      size = pages_cnt * PAGE_SIZE

      core.DEBUG('free: address=%s, pages_start=%s, pages_cnt=%s', ADDR_FMT(address), pages_start, pages_cnt)

      core.mmu.cache_controller.release_area_references(address, size)
      # core.cpu.machine.reset_area_flags(core.mmu.pt_address, address, size)

      pg = core.cpu.machine.memory.page(pages_start)
      core.cpu.machine.memory.free_pages(pg, pages_cnt)

      core.REG(Registers.R00).value = 0

    elif op == MMOperationList.UNUSED:
      pages = [pg for pg in core.cpu.machine.memory.pages(pages_start = addr_to_page(segment_addr_to_addr(core.REG(Registers.DS).value, 0)), pages_cnt = SEGMENT_SIZE, ignore_missing = True)]

      for pg in pages:
        core.DEBUG('used page: pg=%s', pg)

      core.DEBUG('unused: allocated_pages=%i', len(pages))

      core.REG(Registers.R00).value = SEGMENT_SIZE - len(pages)

    elif op == MMOperationList.MMAP:
      self.op_mmap(core)

    elif op == MMOperationList.UNMMAP:
      self.op_unmmap(core)

    else:
      core.WARN('Unknown mm operation requested: %s', op)
      core.REG(Registers.R00).value = 0xFFFF

VIRTUAL_INTERRUPTS[IRQList.MM.value] = MMInterrupt
