import ctypes
import os

from cpu.registers import FlagsRegister
from mm import PAGE_SIZE, UINT8_FMT, UINT16_FMT, UINT24_FMT, SIZE_FMT, ADDR_FMT
from util import BinaryFile, debug, info
from ctypes import c_ubyte, c_ushort, c_uint, LittleEndianStructure

PATH_MAX = os.pathconf('/tmp', 'PC_PATH_MAX')

class FileHeader(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('magic',   c_ushort),
    ('version', c_ushort),
    ('cpus',    c_ushort),
    ('cores',   c_ushort)
  ]

  def __repr__(self):
    return '<FileHeader: magic=%s, version=%s, cpus=%s, cores=%s>' % (self.magic, self.version, self.cpus, self.cores)

class CPUCoreState(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cpuid',  c_ubyte),
    ('coreid', c_ubyte),
    ('r0',  c_ushort),
    ('r1',  c_ushort),
    ('r2',  c_ushort),
    ('r3',  c_ushort),
    ('r4',  c_ushort),
    ('r5',  c_ushort),
    ('r6',  c_ushort),
    ('r7',  c_ushort),
    ('r8',  c_ushort),
    ('r9',  c_ushort),
    ('r10', c_ushort),
    ('r11', c_ushort),
    ('r12', c_ushort),
    ('fp', c_ushort),
    ('sp', c_ushort),
    ('ds', c_ushort),
    ('cs', c_ushort),
    ('ip', c_ushort),
    ('flags', FlagsRegister),
    ('exit_code', c_ushort),
    ('idle',         c_ubyte, 1),
    ('keep_running', c_ubyte, 1),
    ('__padding__', c_ubyte)
  ]

class MemorySegmentState(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index', c_ushort)
  ]

  def __repr__(self):
    return '<MemorySegmentState: index=%s>' % UINT8_FMT(self.index)

class MemoryPageState(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('index', c_uint),
    ('read', c_ubyte, 1),
    ('write', c_ubyte, 1),
    ('execute', c_ubyte, 1),
    ('dirty', c_ubyte, 1),
    ('content', c_ubyte * PAGE_SIZE)
  ]

  def __repr__(self):
    return '<MemoryPageState: index=%s, r=%s, w=%s, x=%s, d=%s>' % (self.index, self.read, self.write, self.execute, self.dirty)

class MMapAreaState(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('address', c_uint),
    ('size', c_uint),
    ('file_path', c_ubyte * PATH_MAX)
  ]

class MemoryState(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('size', c_uint),
    ('irq_table_address', c_uint),
    ('int_table_address', c_uint),
    ('segments', c_uint),
    ('pages', c_uint)
  ]

  def __repr__(self):
    return '<MemoryState: size=%s, irq_table_address=%s, int_table_address=%s, segments=%s, pages=%s>' % (SIZE_FMT(self.size), ADDR_FMT(self.irq_table_address), ADDR_FMT(self.int_table_address), SIZE_FMT(self.segments), SIZE_FMT(self.pages))

class VMState(object):
  def __init__(self):
    super(VMState, self).__init__()

    self.magic = None
    self.version = None

    self.nr_cpus = None
    self.nr_cores = None

    self.core_states = []
    self.mm_state = None
    self.mm_segment_states = []
    self.mm_page_states = []

  @staticmethod
  def capture_vm_state(vm, suspend = True):
    debug('capture_vm_state')

    state = VMState()

    if suspend:
      debug('suspend vm...')
      vm.suspend()

    debug('capture state...')
    state.nr_cpus = vm.nr_cpus
    state.nr_cores = vm.nr_cores

    for _cpu in vm.cpus:
      for _core in _cpu.cores:
        _core.save_state(state)

    vm.memory.save_state(state)

    if suspend:
      debug('wake vm up...')
      vm.wake_up()

    return state

  @staticmethod
  def load_vm_state(filename):
    return CoreDumpFile(filename, 'r').load()

  def save(self, filename):
    f_out = CoreDumpFile(filename, 'w')
    f_out.save(self)

class CoreDumpFile(BinaryFile):
  MAGIC = 0xF00B
  VERSION = 1

  def __init__(self, *args, **kwargs):
    super(CoreDumpFile, self).__init__(*args, **kwargs)

    self.__header = None

  def create_header(self):
    self.__header = FileHeader()
    self.__header.magic = CoreDumpFile.MAGIC
    self.__header.version = CoreDumpFile.VERSION

  def get_header(self):
    return self.__header

  def load(self):
    state = VMState()

    self.seek(0)

    self.__header = self.read_struct(FileHeader)

    state.magic = self.__header.magic
    state.version = self.__header.version
    state.nr_cpus = self.__header.cpus
    state.nr_cores = self.__header.cores

    state.core_states = map(self.read_struct, [CPUCoreState for _ in range(0, self.__header.cpus * self.__header.cores)])
    state.mm_state = self.read_struct(MemoryState)
    state.mm_segment_states = map(self.read_struct, [MemorySegmentState for _ in range(0, state.mm_state.segments)])
    state.mm_page_states = map(self.read_struct, [MemoryPageState for _ in range(0, state.mm_state.pages)])

    return state

  def save(self, state):
    debug('coredump.save: state=%s', state)

    self.seek(0)

    self.create_header()

    self.__header.cpus = state.nr_cpus
    self.__header.cores = state.nr_cores

    self.write_struct(self.__header)

    map(self.write_struct, state.core_states)
    self.write_struct(state.mm_state)
    map(self.write_struct, state.mm_segment_states)
    map(self.write_struct, state.mm_page_states)

