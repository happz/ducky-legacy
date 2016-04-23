from six import iteritems, itervalues
from six.moves import range

from ..interfaces import ISnapshotable
from ..errors import AccessViolationError, InvalidResourceError
from ..util import align, sizeof_fmt, Flags
from ..snapshot import SnapshotNode

import enum

# Types
from ctypes import c_byte as i8_t     # NOQA
from ctypes import c_short as i16_t   # NOQA
from ctypes import c_int as i32_t     # NOQA
from ctypes import c_int64 as i64_t   # NOQA

from ctypes import c_ubyte as u8_t    # NOQA
from ctypes import c_ushort as u16_t  # NOQA
from ctypes import c_uint as u32_t    # NOQA
from ctypes import c_uint64 as u64_t  # NOQA

WORD_SIZE  = 4
SHORT_SIZE = 2

PAGE_SHIFT = 8
#: Size of memory page, in bytes.
PAGE_SIZE = (1 << PAGE_SHIFT)
PAGE_MASK = (~(PAGE_SIZE - 1))

MINIMAL_SIZE = 16

class MMOperationList(enum.IntEnum):
  ALLOC    = 3
  FREE     = 4
  UNUSED   = 5
  MMAP     = 6
  UNMMAP   = 7

from ..util import UINT8_FMT, UINT16_FMT, UINT32_FMT, UINT64_FMT  # noqa

def SIZE_FMT(size):
  return str(size)

def OFFSET_FMT(offset):
  s = '-' if offset < 0 else ''

  return '{}0x{:04X}'.format(s, abs(offset))

class MalformedBinaryError(Exception):
  pass

def addr_to_page(addr):
  return (addr & PAGE_MASK) >> PAGE_SHIFT

def addr_to_offset(addr):
  return addr & (PAGE_SIZE - 1)

def area_to_pages(addr, size):
  return ((addr & PAGE_MASK) >> PAGE_SHIFT, align(PAGE_SIZE, size) // PAGE_SIZE)

class PageTableEntry(Flags):
  _flags = ['read', 'write', 'execute', 'dirty']
  _labels = 'RWXD'

  READ    = 0x01
  WRITE   = 0x02
  EXECUTE = 0x04
  DIRTY   = 0x08

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

  def __repr__(self):
    return '<%s index=%i, base=%s>' % (self.__class__.__name__, self.index, UINT32_FMT(self.base_address))

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

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

  def read_u16(self, offset):
    """
    Read word.

    This operation is implemented by child classes.

    :param int offset: offset of requested word.
    :rtype: int
    """

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

  def read_u32(self, offset):
    """
    Read longword.

    This operation is implemented by child classes.

    :param int offset: offset of requested longword.
    :rtype: int
    """

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

  def write_u8(self, offset, value):
    """
    Write byte.

    This operation is implemented by child classes.

    :param int offset: offset of requested byte.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

  def write_u16(self, offset, value):
    """
    Write word.

    This operation is implemented by child classes.

    :param int offset: offset of requested word.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

  def write_u32(self, offset, value):
    """
    Write longword.

    This operation is implemented by child classes.

    :param int offset: offset of requested longword.
    :param int value: value to write into memory.
    """

    raise NotImplementedError('Not allowed to access memory on this address: page={}, offset={}'.format(self.index, offset))

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
    return '<%s index=%i, base=%s, offset=%s>' % (self.__class__.__name__, self.index, UINT32_FMT(self.base_address), UINT32_FMT(self.offset))

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
    state.flags = self.flags.to_int()
    state.pages_start = self.pages_start
    state.pages_cnt = self.pages_cnt

  def load_state(self, state):
    pass

class MemoryState(SnapshotNode):
  def __init__(self):
    super(MemoryState, self).__init__('size')

  def get_page_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('page_')]

class MemoryController(object):
  """
  Memory controller handles all operations regarding main memory.

  :param ducky.machine.Machine machine: virtual machine that owns this controller.
  :param int size: size of memory, in bytes.
  :raises ducky.errors.InvalidResourceError: when memory size is not multiple of
    :py:data:`ducky.mm.PAGE_SIZE`.
  """

  def __init__(self, machine, size = 0x1000000):
    machine.DEBUG('%s: size=0x%X', self.__class__.__name__, size)

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if size < MINIMAL_SIZE * PAGE_SIZE:
      raise InvalidResourceError('Memory size must be at least %d pages' % MINIMAL_SIZE)

    self.machine = machine

    # Setup logging - create our local shortcuts to machine' logger
    self.DEBUG = self.machine.DEBUG
    self.INFO = self.machine.INFO
    self.WARN = self.machine.WARN
    self.ERROR = self.machine.ERROR
    self.EXCEPTION = self.machine.EXCEPTION

    self.force_aligned_access = self.machine.config.getbool('memory', 'force-aligned-access', default = False)

    self.size = size
    self.pages_cnt = size // PAGE_SIZE
    self.pages = {}

  def save_state(self, parent):
    self.DEBUG('mc.save_state')

    state = parent.add_child('memory', MemoryState())

    state.size = self.size

    for page in itervalues(self.pages):
      page.save_state(state)

  def load_state(self, state):
    self.size = state.size

    for page_state in state.get_children():
      page = self.get_page(page_state.index)
      page.load_state(page_state)

  def __set_page(self, pg):
    """
    Install page object for a specific memory page.

    :param ducky.mm.MemoryPage pg: page to be installed
    :returns: installed page
    :rtype: :py:class:`ducky.mm.MemoryPage`
    """

    assert pg.index not in self.pages

    if pg.index >= self.pages_cnt:
      raise InvalidResourceError('Attempt to create page with index out of bounds: pg.index=%d' % pg.index)

    self.pages[pg.index] = pg
    return pg

  def __remove_page(self, pg):
    """
    Removes page object for a specific memory page.

    :param ducky.mm.MemoryPage pg: page to be removed
    """

    assert pg.index in self.pages

    del self.pages[pg.index]

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

    if index in self.pages:
      raise AccessViolationError('Page {} is already allocated'.format(index))

    return self.__alloc_page(index)

  def alloc_pages(self, base = None, count = 1):
    """
    Allocate continuous sequence of anonymous pages.

    :param u24 base: if set, start searching pages from this address.
    :param int count: number of requested pages.
    :returns: list of newly allocated pages.
    :rtype: ``list`` of :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.InvalidResourceError: when there is no available sequence of
      pages.
    """

    self.DEBUG('mc.alloc_pages: base=%s, count=%s', UINT32_FMT(base) if base is not None else '<none>', count)

    if base is not None:
      pages_start = base // PAGE_SIZE
      pages_cnt = self.pages_cnt - pages_start
    else:
      pages_start = 0
      pages_cnt = self.pages_cnt

    self.DEBUG('mc.alloc_pages: page=%s, cnt=%s', pages_start, pages_cnt)

    for i in range(pages_start, pages_start + pages_cnt):
      for j in range(i, i + count):
        if j in self.pages:
          break

      else:
        return [self.__alloc_page(j) for j in range(i, i + count)]

    raise InvalidResourceError('No sequence of free pages available')

  def alloc_page(self, base = None):
    """
    Allocate new anonymous page for usage. The first available index is used.

    :param int base: if set, start searching pages from this address.
    :returns: newly reserved page.
    :rtype: :py:class:`ducky.mm.AnonymousMemoryPage`
    :raises ducky.errors.InvalidResourceError: when there is no available page.
    """

    self.DEBUG('mc.alloc_page: base=%s', UINT32_FMT(base) if base is not None else '<none>')

    if base is not None:
      pages_start = base // PAGE_SIZE
      pages_cnt = self.pages_cnt - pages_start
    else:
      pages_start = 0
      pages_cnt = self.pages_cnt

    self.DEBUG('mc.alloc_page: page=%s, cnt=%s', pages_start, pages_cnt)

    for i in range(pages_start, pages_start + pages_cnt):
      if i not in self.pages:
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

    if pg.index in self.pages:
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

    if pg.index not in self.pages:
      raise AccessViolationError('Page {} is not allocated'.format(pg.index))

    self.__remove_page(pg)

  def free_page(self, page):
    """
    Free memory page when it's no longer needed.

    :param ducky.mm.MemoryPage page: page to be freed.
    """

    self.DEBUG('mc.free_page: page=%i, base=%s', page.index, UINT32_FMT(page.base_address))

    self.__remove_page(page)

  def free_pages(self, page, count = 1):
    """
    Free a continuous sequence of pages when they are no longer needed.

    :param ducky.mm.MemoryPage page: first page in series.
    :param int count: number of pages.
    """

    self.DEBUG('mc.free_pages: page=%i, base=%s, count=%s', page.index, UINT32_FMT(page.base_address), count)

    for i in range(page.index, page.index + count):
      self.free_page(self.pages[i])

  def get_page(self, index):
    """
    Return memory page, specified by its index from the beginning of memory.

    :param int index: index of requested page.
    :rtype: :py:class:`ducky.mm.MemoryPage`
    :raises ducky.errors.AccessViolationError: when requested page is not allocated.
    """

    if index not in self.pages:
      return self.alloc_specific_page(index)
      # raise AccessViolationError('Page {} not allocated yet'.format(index))

    return self.pages[index]

  def get_pages(self, pages_start = 0, pages_cnt = None, ignore_missing = False):
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

    pages_cnt = pages_cnt or self.pages_cnt

    if ignore_missing is True:
      return (self.pages[i] for i in range(pages_start, pages_start + pages_cnt) if i in self.pages)
    else:
      return (self.pages[i] for i in range(pages_start, pages_start + pages_cnt))

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

    self.DEBUG('mc.pages_in_area: address=%s, size=%s', UINT32_FMT(address), size)

    size = size or self.size
    pages_start, pages_cnt = area_to_pages(address, size)

    return self.get_pages(pages_start = pages_start, pages_cnt = pages_cnt, ignore_missing = ignore_missing)

  def boot(self):
    """
    Prepare memory controller for immediate usage by other components.
    """

    self.machine.tenh('mm: %s, %s available', sizeof_fmt(self.size, max_unit = 'Ki'), sizeof_fmt(self.size - len(self.pages) * PAGE_SIZE, max_unit = 'Ki'))

  def halt(self):
    pass

  def read_u8(self, addr):
    self.DEBUG('mc.read_u8: addr=%s', UINT32_FMT(addr))

    return self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u8(addr & (PAGE_SIZE - 1))

  def read_u16(self, addr):
    self.DEBUG('mc.read_u16: addr=%s', UINT32_FMT(addr))

    return self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u16(addr & (PAGE_SIZE - 1))

  def read_u32(self, addr):
    self.DEBUG('mc.read_u32: addr=%s', UINT32_FMT(addr))

    return self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).read_u32(addr & (PAGE_SIZE - 1))

  def write_u8(self, addr, value):
    self.DEBUG('mc.write_u8: addr=%s, value=%s', UINT32_FMT(addr), UINT8_FMT(value))

    self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u8(addr & (PAGE_SIZE - 1), value)

  def write_u16(self, addr, value):
    self.DEBUG('mc.write_u16: addr=%s, value=%s', UINT32_FMT(addr), UINT16_FMT(value))

    self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u16(addr & (PAGE_SIZE - 1), value)

  def write_u32(self, addr, value):
    self.DEBUG('mc.write_u32: addr=%s, value=%s', UINT32_FMT(addr), UINT32_FMT(value))

    self.get_page((addr & PAGE_MASK) >> PAGE_SHIFT).write_u32(addr & (PAGE_SIZE - 1), value)
