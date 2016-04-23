"""
This file provides necessary code to allow boot up of a virtual machine with
the correct program running. This code can provide slightly different environment
when compared to real hardware process, since e.g. external files can be mmap-ed
into VM's memory for writing.
"""

import importlib
import mmap

from functools import partial
from ctypes import sizeof
from six import PY2

from .interfaces import IMachineWorker

from .errors import InvalidResourceError
from .util import align, BinaryFile
from .mm import u8_t, u16_t, u32_t, UINT32_FMT, PAGE_SIZE, area_to_pages, PAGE_MASK, ExternalMemoryPage
from .mm.binary import SectionFlags, File, SectionTypes
from .snapshot import SnapshotNode
from .hdt import HDT, HDTEntry_Argument
from .debugging import Point  # noqa

#: By default, Hardware Description Table starts at this address after boot.
DEFAULT_HDT_ADDRESS        = 0x00000100

#: By default, CPU starts executing instructions at this address after boot.
DEFAULT_BOOTLOADER_ADDRESS = 0x00020000

class MMapMemoryPage(ExternalMemoryPage):
  """
  Memory page backed by an external file that is accessible via ``mmap()``
  call. It's a part of one of mm.MMapArea instances, and if such area was
  opened as `shared`, every change in this page content will affect the
  content of external file, and vice versa, every change of external file
  will be reflected in content of this page (if this page lies in affected
  area).

  :param MMapArea area: area this page belongs to.
  """

  def __init__(self, area, *args, **kwargs):
    super(MMapMemoryPage, self).__init__(*args, **kwargs)

    self.area = area

    if PY2:
      self.get, self.put = self._get_py2, self._put_py2

    else:
      self.get, self.put = self._get_py3, self._put_py3

  def get(self, offset):
    """
    Read one byte from page.

    This is an abstract method, `__init__` is expected to replace it with
    a method, tailored for the Python version used.

    :param int offset: offset of the requested byte.
    :rtype: int
    """

    raise NotImplementedError()

  def put(self, offset, b):
    """
    Write one byte to page.

    This is an abstract method, `__init__` is expected to replace it with
    a method, tailored for the Python version used.

    :param int offset: offset of the modified byte.
    :param int b: new value of the modified byte.
    """

    raise NotImplementedError()

  def _get_py2(self, offset):
    """
    Read one byte from page.

    :param int offset: offset of the requested byte.
    :rtype: int
    """

    return ord(self.data[self.offset + offset])

  def _put_py2(self, offset, b):
    """
    Write one byte to page.

    :param int offset: offset of the modified byte.
    :param int b: new value of the modified byte.
    """

    self.data[self.offset + offset] = chr(b)

  def _get_py3(self, offset):
    """
    Read one byte from page.

    :param int offset: offset of the requested byte.
    :rtype: int
    """

    return self.data[self.offset + offset]

  def _put_py3(self, offset, b):
    """
    Write one byte to page.

    :param int offset: offset of the modified byte.
    :param int b: new value of the modified byte.
    """

    self.data[self.offset + offset] = b

class MMapAreaState(SnapshotNode):
  def __init__(self):
    super(MMapAreaState, self).__init__('address', 'size', 'path', 'offset')

class MMapArea(object):
  """
  Objects of this class represent one mmaped memory area each, to track this
  information for later use.

  :param ptr: ``mmap object``, as returned by `mmap.mmap` function.
  :param u32_t address: address of the first byte of an area in the memory.
  :param u32_t size: length of the area, in bytes.
  :param file_path: path to a source file.
  :param u32_t offset: offset of the first byte in the source file.
  :param int pages_start: first page of the area.
  :param int pages_cnt: number of pages in the area.
  :param mm.binary.SectionFlags flags: flags applied to this area.
  """

  def __init__(self, ptr, address, size, file_path, offset, pages_start, pages_cnt, flags):
    super(MMapArea, self).__init__()

    self.ptr = ptr
    self.address = address

    self.size = size
    self.file_path = file_path
    self.offset = offset
    self.pages_start = pages_start
    self.pages_cnt = pages_cnt
    self.flags = flags

  def __repr__(self):
    return '<MMapArea: address=%s, size=%s, filepath=%s, pages-start=%s, pages-cnt=%i, flags=%s>' % (UINT32_FMT(self.address), self.size, self.file_path, self.pages_start, self.pages_cnt, self.flags.to_string())

  def save_state(self, parent):
    pass

  def load_state(self, state):
    pass

class ROMLoader(IMachineWorker):
  def __init__(self, machine):
    self.machine = machine
    self.config = machine.config

    self.opened_mmap_files = {}  # path: (cnt, file)
    self.mmap_areas = {}

    self.logger = self.machine.LOGGER
    self.DEBUG = self.machine.DEBUG

  def _get_mmap_fileno(self, file_path):
    if file_path not in self.opened_mmap_files:
      self.opened_mmap_files[file_path] = [0, open(file_path, 'r+b')]

    desc = self.opened_mmap_files[file_path]

    desc[0] += 1
    return desc[1].fileno()

  def _put_mmap_fileno(self, file_path):
    desc = self.opened_mmap_files[file_path]

    desc[0] -= 1
    if desc[0] > 0:
      return

    desc[1].close()
    del self.opened_mmap_files[file_path]

  def mmap_area(self, file_path, address, size, offset = 0, flags = None, shared = False):
    """
    Assign set of memory pages to mirror external file, mapped into memory.

    :param string file_path: path of external file, whose content new area
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

    self.DEBUG('%s.mmap_area: file=%s, offset=%s, size=%s, address=%s, flags=%s, shared=%s', self.__class__.__name__, file_path, offset, size, UINT32_FMT(address), flags.to_string(), shared)

    if size % PAGE_SIZE != 0:
      raise InvalidResourceError('Memory size must be multiple of PAGE_SIZE')

    if address % PAGE_SIZE != 0:
      raise InvalidResourceError('MMap area address must be multiple of PAGE_SIZE')

    mc = self.machine.memory
    pages_start, pages_cnt = area_to_pages(address, size)

    for i in range(pages_start, pages_start + pages_cnt):
      if i in mc.pages:
        raise InvalidResourceError('MMap request overlaps with existing pages: page=%s, area=%s' % (mc.pages[i], mc.pages[i].area))

    mmap_flags = mmap.MAP_SHARED if shared else mmap.MAP_PRIVATE

    # Always mmap as writable - VM will force read-only access using
    # page flags. But since it is possible to change page flags
    # in run-time, and request write access to areas originaly
    # loaded as read-only, such write access would fail because
    # the underlying mmap area was mmaped as read-only only, and this
    # limitation is not possible to overcome.
    mmap_prot = mmap.PROT_READ | mmap.PROT_WRITE

    ptr = mmap.mmap(
      self._get_mmap_fileno(file_path),
      size,
      flags = mmap_flags,
      prot = mmap_prot,
      offset = offset)

    area = MMapArea(ptr, address, size, file_path, ptr, pages_start, pages_cnt, flags)

    for i in range(pages_start, pages_start + pages_cnt):
      mc.register_page(MMapMemoryPage(area, mc, i, ptr, offset = (i - pages_start) * PAGE_SIZE))

    self.mmap_areas[area.address] = area

    return area

  def unmmap_area(self, mmap_area):
    mc = self.machine.memory

    for pg in mc.get_pages(pages_start = mmap_area.pages_start, pages_cnt = mmap_area.pages_cnt):
      mc.unregister_page(pg)

    del self.mmap_areas[mmap_area.address]

    mmap_area.ptr.close()

    self._put_mmap_fileno(mmap_area.file_path)

  def setup_hdt(self):
    """
    Initialize memory area that contains HDT.

    If VM config file specifies HDT image file, it is loaded, otherwise HDT
    is constructed for the actual configuration. It is then copied into memory.

    :param u32_t machine.hdt-address: Base address of HDT in memory. If not set,
      :py:const:`ducky.boot.DEFAULT_HDT_ADDRESS` is used.
    :param machine.hdt-image: HDT image to load. If not set, HDT is constructed
      for the actual VM's configuration.
    """

    self.DEBUG('%s.setup_hdt', self.__class__.__name__)

    hdt_address = self.config.getint('machine', 'hdt-address', DEFAULT_HDT_ADDRESS)
    if hdt_address & ~PAGE_MASK:
      raise InvalidResourceError('HDT address must be page-aligned: address=%s' % UINT32_FMT(hdt_address))

    self.DEBUG('HDT address=%s', UINT32_FMT(hdt_address))

    def __alloc_pages(size):
      pages = self.machine.memory.alloc_pages(base = hdt_address, count = align(PAGE_SIZE, size) // PAGE_SIZE)
      self.machine.DEBUG('%s.setup_hdt: address=%s, size=%s (%s pages)', self.__class__.__name__, UINT32_FMT(hdt_address), size, len(pages))

    hdt_image = self.config.get('machine', 'hdt-image', None)
    if hdt_image is None:
      self.DEBUG('HDT image not specified, creating one')

      hdt = HDT(self.machine.LOGGER, config = self.config)
      hdt.create()

      __alloc_pages(len(hdt))

      def __write_field(writer_fn, size, address, field_value):
        writer_fn(address, field_value)
        return address + size

      def __write_array(max_length, address, field_value):
        for i in range(0, max_length):
          self.machine.memory.write_u8(address + i, field_value[i])

        return address + max_length

      def __write_struct(address, struct):
        for n, t in struct._fields_:
          address = writers[sizeof(t)](address, getattr(struct, n))

        return address

      writers = {
        1: partial(__write_field, self.machine.memory.write_u8,  1),
        2: partial(__write_field, self.machine.memory.write_u16, 2),
        4: partial(__write_field, self.machine.memory.write_u32, 4),
        HDTEntry_Argument.MAX_NAME_LENGTH: partial(__write_array, HDTEntry_Argument.MAX_NAME_LENGTH)
      }

      address = __write_struct(hdt_address, hdt.header)

      for entry in hdt.entries:
        address = __write_struct(address, entry)

    else:
      self.DEBUG('Loading HDT image %s', hdt_image)

      with BinaryFile.open(self.logger, hdt_image, 'r') as f_in:
        img = f_in.read()

      __alloc_pages(len(img))

      for address, b in zip(range(hdt_address, hdt_address + len(img)), img):
        self.machine.memory.write_u8(address, b)

  def setup_mmaps(self):
    self.DEBUG('%s.setup_mmaps', self.__class__.__name__)

    for section in self.config.iter_mmaps():
      _get, _getbool, _getint = self.config.create_getters(section)

      access = _get('access', 'r')
      flags = SectionFlags.create(readable = 'r' in access, writable = 'w' in access, executable = 'x' in access)
      self.mmap_area(_get('file'), _getint('address'), _getint('size'), offset = _getint('offset', 0), flags = flags, shared = _getbool('shared', False))

  def setup_debugging(self):
    self.DEBUG('%s.setup_debugging', self.__class__.__name__)

    for section in self.config.iter_breakpoints():
      _get, _getint, _getbool = self.config.create_getters(section)

      core = self.machine.core(_get('core', '#0:#0'))
      core.init_debug_set()

      klass = _get('klass', 'ducky.debugging.BreakPoint').split('.')
      klass = getattr(importlib.import_module('.'.join(klass[0:-1])), klass[-1])

      p = klass.create_from_config(core.debug, self.config, section)
      core.debug.add_point(p, _get('chain', 'pre-step'))

      for action_section in _get('actions', '').split(','):
        action_section = action_section.strip()
        if not action_section:
          continue

        klass = self.config.get(action_section, 'klass').split('.')
        klass = getattr(importlib.import_module('.'.join(klass[0:-1])), klass[-1])

        a = klass.create_from_config(core.debug, self.config, action_section)
        p.actions.append(a)

  def __load_content(self, base, content):
    from .cpu.assemble import SpaceSlot

    ptr = base

    self.DEBUG('%s.__load_content: base=%s, items=%s', self.__class__.__name__, UINT32_FMT(base), len(content))

    def __write(writer, size, value):
      writer(ptr, value)
      return ptr + size

    writers = {
      1: partial(__write, self.machine.memory.write_u8,  1),
      2: partial(__write, self.machine.memory.write_u16, 2),
      4: partial(__write, self.machine.memory.write_u32, 4)
    }

    for i in content:
      self.DEBUG('%s.__load_content: ptr=%s, i=%s', self.__class__.__name__, UINT32_FMT(ptr), UINT32_FMT(i))

      if isinstance(i, SpaceSlot):
        ptr += i.size

      else:
        ptr = writers[sizeof(i)](i.value)

  def load_text(self, base, content):
    self.DEBUG('%s.load_text: base=%s', self.__class__.__name__, UINT32_FMT(base))

    self.__load_content(base, content)

  def load_data(self, base, content):
    self.DEBUG('%s.load_data: base=%s', self.__class__.__name__, UINT32_FMT(base))

    self.__load_content(base, content)

  def setup_bootloader(self, filepath, base = None):
    self.DEBUG('%s.setup_bootloader: filepath=%s, base=%s', self.__class__.__name__, filepath, UINT32_FMT(base) if base is not None else '<none>')

    base = base or DEFAULT_BOOTLOADER_ADDRESS
    mc = self.machine.memory

    with File.open(self.machine.LOGGER, filepath, 'r') as f:
      f.load()

      f_header = f.get_header()

      for i in range(0, f_header.sections):
        s_header, s_content = f.get_section(i)

        s_base = s_header.base

        self.DEBUG('%s.setup_bootloader: section=%s, base=%s', self.__class__.__name__, f.string_table.get_string(s_header.name), UINT32_FMT(s_base))

        if s_header.type == SectionTypes.SYMBOLS:
          continue

        if s_header.flags.loadable != 1:
          continue

        s_base = base + s_base

        pages_start, pages_cnt = area_to_pages(s_base, s_header.file_size)

        if f_header.flags.mmapable == 1:
          # Always mmap sections as RW, and disable W if section' flags requires that
          # Otherwise, when program asks Vm to enable W, any access would fail because
          # the underlying mmap area was not mmaped as writable
          self.mmap_area(f.name, s_base, s_header.file_size, offset = s_header.offset, flags = SectionFlags.from_encoding(s_header.flags), shared = False)

        else:
          for i in range(pages_start, pages_start + pages_cnt):
            mc.alloc_specific_page(i)

          if s_header.type == SectionTypes.TEXT:
            self.load_text(s_base, s_content)

          elif s_header.type == SectionTypes.DATA and s_header.flags.bss != 1:
            self.load_data(s_base, s_content)

  def poke(self, address, value, length):
    self.DEBUG('%s.poke: addr=%s, value=%s, length=%s', self.__class__.__name__, UINT32_FMT(address), UINT32_FMT(value), length)

    if length == 1:
      self.machine.memory.write_u8(address, u8_t(value).value)

    elif length == 2:
      self.machine.memory.write_u16(address, u16_t(value).value)

    else:
      self.machine.memory.write_u32(address, u32_t(value).value)

  def boot(self):
    self.DEBUG('%s.boot', self.__class__.__name__)

    self.setup_hdt()
    self.setup_mmaps()
    self.setup_debugging()

    if self.config.has_section('bootloader'):
      self.setup_bootloader(self.config.get('bootloader', 'file'))

  def halt(self):
    self.DEBUG('%s.halt', self.__class__.__name__)

    for area in list(self.mmap_areas.values()):
      self.unmmap_area(area)
