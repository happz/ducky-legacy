"""
SimpleVGA is very basic implementation of VGA-like device, with text
and graphic modes.
"""

import array
import enum
import functools

from six.moves import range

from ctypes import c_ushort, LittleEndianStructure

from . import Device, IOProvider
from ..errors import InvalidResourceError
from ..mm import PAGE_SIZE, ExternalMemoryPage, addr_to_page, UInt8
from ..util import sizeof_fmt, F, UINT16_FMT, ADDR_FMT
from ..reactor import RunInIntervalTask
from ..streams import OutputStream

#: Default address of command port
DEFAULT_PORT_RANGE = 0x3F0
#: Default memory size, in bytes
DEFAULT_MEMORY_SIZE = 64 * 1024
#: Default number of memory banks
DEFAULT_MEMORY_BANKS = 8


class SimpleVGACommands(enum.IntEnum):
  RESET          = 0x8001
  REFRESH        = 0x0002

  GRAPHIC        = 0x0020
  COLS           = 0x0021
  ROWS           = 0x0022
  DEPTH          = 0x0023

  MEMORY_BANK_ID = 0x0030


class Mode(object):
  def __init__(self, _type, width, height, depth):
    self.type = _type
    self.width = width
    self.height = height
    self.depth = depth

    self.required_memory = self.width * self.height * (self.depth if self.type == 't' else self.depth // 8)

  def __cmp__(self, other):
    return self.type == other.type and self.width == other.width and self.height == other.height and self.depth == other.depth

  def __eq__(self, other):
    return self.__cmp__(other)

  def __repr__(self):
    return self.to_string()

  @classmethod
  def from_string(cls, s):
    """
    Create ``Mode`` object from its string representation. It's a comma-separated
    list of for items:

    +--------------+----------+-----------------+-----------------------+-----------------+
    |              | ``type`` | ``width``       | ``height``            | ``depth``       |
    +--------------+----------+-----------------+-----------------------+-----------------+
    | Text mode    | ``t``    | chars per line  | lines on screen       | bytes per char  |
    +--------------+----------+-----------------+-----------------------+-----------------+
    | Graphic mode | ``g``    | pixels per line | pixel lines on screen | bites per pixel |
    +--------------+----------+-----------------+-----------------------+-----------------+
    """

    t, c, r, b = s.strip().split(',')
    return cls(t, int(c.strip()), int(r.strip()), int(b.strip()))

  def to_string(self):
    return F('({type}, {width}, {height}, {depth})', type = self.type, width = self.width, height = self.height, depth = self.depth)

  def to_pretty_string(self):
    return F('{type}, {cols}x{rows} {entities}, {memory_per_entity} {memory_label}',
             type = 'text' if self.type == 't' else 'graphic',
             cols = self.width,
             rows = self.height,
             entities = 'chars' if self.type == 't' else 'pixels',
             memory_per_entity = self.depth if self.type == 't' else self.depth * 8,
             memory_label = 'bytes per char' if self.type == 't' else 'bits color depth'
             )

#: Default list of available modes
DEFAULT_MODES = [
  Mode('g', 320, 200, 1),
  Mode('t', 80, 25, 2),
  Mode('t', 80, 25, 1)
]
#: Default boot mode
DEFAULT_BOOT_MODE = Mode('t', 80, 25, 1)

class Char(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('codepoint', c_ushort, 7),
    ('unused',    c_ushort, 1),
    ('fg',        c_ushort, 4),
    ('bg',        c_ushort, 3),
    ('blink',     c_ushort, 1)
  ]

  def to_u8(self):
    return (UInt8(self.codepoint | self.unused << 7).value, UInt8(self.fg | self.bg << 4 | self.blink << 7).value)

  @staticmethod
  def from_u8(l, h):
    c = Char()
    c.codepoint = l & 0x7F
    c.fg = h & 0x0F
    c.bg = (h >> 4) & 0x07
    c.blink = h >> 7
    return c

  @staticmethod
  def from_u16(u):
    return Char.from_u8(u & 0x00FF, u >> 8)

class DisplayRefreshTask(RunInIntervalTask):
  def __init__(self, display):
    super(DisplayRefreshTask, self).__init__(200, self.on_tick)

    self.display = display
    self.first_tick = True

    self.write = display.stream_out.write

  def on_tick(self, task):
    self.display.machine.DEBUG('Display: refresh display')

    gpu = self.display.gpu
    mode = gpu.active_mode

    palette_fg = [30, 34, 32, 36, 31, 35, 31, 37,  90,  94,  92,  96,  91,  95, 33,  97]
    palette_bg = [40, 44, 42, 46, 41, 45, 41, 47, 100, 104, 102, 106, 101, 105, 43, 107]

    if mode.type == 't':
      screen = []

      if mode.depth not in (1, 2):
        self.display.machine.WARN(F('Unhandled character depth: mode={mode}', mode = self.active_mode))
        return

      for row in range(0, mode.height):
        line = []

        for col in range(0, mode.width):
          if mode.depth == 1:
            c = Char.from_u8(gpu.memory[row * mode.width + col], 0)
            c.fg = 15
            c.bg = 0

          else:
            c = Char.from_u8(gpu.memory[(row * mode.width + col) * 2], gpu.memory[(row * mode.width + col) * 2 + 1])

          char = F('\033[{blink:d};{fg:d};{bg:d}m{char}\033[0m',
                   blink = 5 if c.blink == 1 else 0,
                   fg = palette_fg[c.fg],
                   bg = palette_bg[c.bg],
                   char = ' ' if c.codepoint == 0 else chr(c.codepoint)
                   )
          line.append(char)

        screen.append(''.join(line))

      def __line(l):
        return [ord(c) for c in l] + [ord('\n')]

      if self.first_tick:
        self.first_tick = False
      else:
        self.write(__line(F('\033[{rows:d}F', rows = mode.height + 3)))

      self.write(__line('-' * mode.width))
      for line in screen:
        self.write(__line(line))
      self.write(__line('-' * mode.width))

    else:
      self.display.machine.WARN(F('Unhandled gpu mode: mode={mode}', mode = gpu.active_mode))

class Display(Device):
  def __init__(self, machine, name, gpu = None, stream_out = None, *args, **kwargs):
    super(Display, self).__init__(machine, 'display', name, *args, **kwargs)

    self.gpu = gpu
    self.stream_out = stream_out

    self.gpu.master = self

    self.refresh_task = DisplayRefreshTask(self)

  @staticmethod
  def get_slave_gpu(machine, config, section):
    gpu_name = config.get(section, 'gpu', None)
    gpu_device = machine.get_device_by_name(gpu_name)

    if not gpu_name or not gpu_device:
      raise InvalidResourceError(F('Unknown GPU device: gpu={name}', name = gpu_name))

    return gpu_device

  @staticmethod
  def create_from_config(machine, config, section):
    gpu = Display.get_slave_gpu(machine, config, section)
    stream_out =  OutputStream.create(machine.LOGGER, config.get(section, 'stream_out', '<stdout>'))

    return Display(machine, section, gpu = gpu, stream_out = stream_out)

  def boot(self):
    self.machine.DEBUG('Display.boot')

    super(Display, self).boot()

    self.gpu.boot()
    self.machine.reactor.add_task(self.refresh_task)
    self.machine.reactor.task_runnable(self.refresh_task)

    self.machine.INFO(F('display: generic {name} connected to gpu {gpu}, output stream {stream}', name = self.name, gpu = self.gpu.name, stream = self.stream_out))

  def halt(self):
    self.machine.DEBUG('Display.halt')

    super(Display, self).halt()

    self.machine.reactor.remove_task(self.refresh_task)
    self.gpu.halt()

    self.machine.DEBUG('Display: halted')


class SimpleVGAMemoryPage(ExternalMemoryPage):
  """
  Memory page handling MMIO of sVGA device.

  :param ducky.devices.svga.SimpleVGA dev: sVGA device this page belongs to.
  """

  def __init__(self, dev, *args, **kwargs):
    super(SimpleVGAMemoryPage, self).__init__(*args, **kwargs)

    self.dev = dev

  def get(self, offset):
    return self.data[self.dev.bank_offsets[self.dev.active_bank] + self.offset + offset]

  def put(self, offset, b):
    self.data[self.dev.bank_offsets[self.dev.active_bank] + self.offset + offset] = b

class SimpleVGA(IOProvider, Device):
  """
  SimpleVGA is very basic implementation of VGA-like device, with text
  and graphic modes.

  It has its own graphic memory ("buffer"), split into several banks of
  the same size. Always only one bank can be directly accessed, by having
  it mapped into CPU's address space.

  :param ducky.machine.Machine machine: machine this device belongs to.
  :param string name: name of this device.
  :param u16 port: address of the command port.
  :param int memory_size: size of graphic memory.
  :param u24 memory_address: address of graphic memory - to this address is
    graphic buffer mapped. Must be specified, there is no default value.
  :param int memory_banks: number of memory banks.
  :param list modes: list of :py:class:`ducky.devices.svga.Mode` objects,
    list of supported modes.
  :param tuple boot_mode: this mode will be set when device boots up.
  """

  def __init__(self, machine, name, port = None, memory_size = None, memory_address = None, memory_banks = None, modes = None, boot_mode = None, *args, **kwargs):
    if memory_address is None:
      raise InvalidResourceError('sVGA device memory address must be specified explicitly')

    if memory_address % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory address must be page-aligned')

    super(SimpleVGA, self).__init__(machine, 'gpu', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = [port, port + 0x0001]

    self.memory_size = memory_size or DEFAULT_MEMORY_SIZE
    self.memory_address = memory_address
    self.memory_banks = memory_banks or DEFAULT_MEMORY_BANKS
    self.modes = modes or DEFAULT_MODES

    if self.memory_size % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory size must be page-aligned')

    if (self.memory_size // self.memory_banks) % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory bank size must be page-aligned')

    self.active_mode = None
    self.boot_mode = boot_mode or DEFAULT_BOOT_MODE

    if self.boot_mode not in self.modes:
      raise InvalidResourceError(F('Boot mode not available: boot_mode={mode}, modes={modes}', mode = self.boot_mode, modes = self.modes))

    for mode in self.modes:
      if mode.required_memory > self.memory_size:
        raise InvalidResourceError(F('Not enough memory for mode: mode={mode}, required={bytes_required:d} bytes, available={bytes_available:d} bytes', mode = mode, bytes_required = mode.required_memory, bytes_available = self.memory_size))

    self.memory = self.data = array.array('B', [0 for _ in range(0, self.memory_size)])
    self.bank_offsets = list(range(0, self.memory_size, self.memory_size // self.memory_banks))
    self.pages_per_bank = self.memory_size // PAGE_SIZE // self.memory_banks

    self.machine.DEBUG(F('sVGA: memory-size={memory_size:d}, memory-banks={memory_banks:d}, offsets=[{bank_offsets}], pages-per-bank={pages_per_bank:d}, address={address:A}', memory_size = self.memory_size, memory_banks = self.memory_banks, bank_offsets = ', '.join([ADDR_FMT(o) for o in self.bank_offsets]), pages_per_bank = self.pages_per_bank, address = self.memory_address))

  @staticmethod
  def create_from_config(machine, config, section):
    _getint = functools.partial(config.getint, section)

    def parse_mode(m):
      t, c, r, b = m.strip().split(',')
      return (t, int(c.strip()), int(r.strip()), int(b.strip()))

    modes = config.get(section, 'modes', None)
    if modes is not None:
      modes = [Mode.from_string(m) for m in modes.split(';')]

    boot_mode = config.get(section, 'boot-mode', None)
    if boot_mode is not None:
      boot_mode = Mode.from_string(boot_mode)

    return SimpleVGA(machine, section,
                     port = _getint('port', DEFAULT_PORT_RANGE),
                     memory_size = _getint('memory-size', DEFAULT_MEMORY_SIZE),
                     memory_address = _getint('memory-address', None),
                     memory_banks = _getint('memory-banks', DEFAULT_MEMORY_BANKS),
                     modes = modes,
                     boot_mode = boot_mode)

  def __repr__(self):
    return F('sVGA adapter {name} ({memory_size} VRAM in {memory_banks:d} banks at {memory_address}, control [{ports}]; {mode} mode)',
             name = self.name,
             memory_size = sizeof_fmt(self.memory_size),
             memory_banks = self.memory_banks,
             memory_address = ADDR_FMT(self.memory_address),
             ports = ', '.join([UINT16_FMT(port) for port in self.ports]),
             mode = self.active_mode.to_pretty_string() if self.active_mode is not None else (self.boot_mode.to_pretty_string() + ' boot')
             )

  def reset(self):
    self.state = None
    self.active_mode = None
    self.active_bank = 0

    for pg in self.pages:
      pg.clear()

  def set_mode(self, mode):
    self.active_mode = mode

  def boot(self):
    self.machine.DEBUG('SimpleVGA.boot')

    for port in self.ports:
      self.machine.register_port(port, self)

    self.pages = []
    pages_start = addr_to_page(self.memory_address)

    for i in range(pages_start, pages_start + self.pages_per_bank):
      pg = SimpleVGAMemoryPage(self, self.machine.memory, i, self.memory, offset = (i - pages_start) * PAGE_SIZE)
      pg.flags_reset()
      pg.read = True
      pg.write = True
      pg.cache = False

      self.machine.memory.register_page(pg)
      self.pages.append(pg)

    self.reset()
    self.set_mode(self.boot_mode)

    self.machine.INFO(F('gpu: {gpu}', gpu = self))

  def halt(self):
    self.machine.DEBUG('SimpleVGA.halt')

    for pg in self.pages:
      self.machine.memory.unregister_page(pg)

    self.pages = []

    for port in self.ports:
      self.machine.unregister_port(port)

    self.machine.DEBUG('SimpleVGA: halted')

  def read_u16(self, port):
    self.machine.DEBUG(F('{method}.read_u16: port={port:W}', method = self.__class__.__name__, port = port))

    if port != self.ports[1]:
      raise InvalidResourceError('Unable to read from command register')

    if self.state == SimpleVGACommands.GRAPHIC:
      self.state = None
      return 1 if self.active_mode.type == 'g' else 0

    if self.state == SimpleVGACommands.COLS:
      self.state = None
      return self.active_mode.width

    if self.state == SimpleVGACommands.ROWS:
      self.state = None
      return self.active_mode.height

    if self.state == SimpleVGACommands.DEPTH:
      self.state = None
      return self.active_mode.depth

    if self.state == SimpleVGACommands.MEMORY_BANK_ID:
      self.state = None
      return self.active_bank

    raise InvalidResourceError(F('Invalid internal state: state={state}', state = self.state))

  def write_u16(self, port, value):
    self.machine.DEBUG(F('{method}.write_u16: port={port:W}, value={value:W}', method = self.__class__.__name__, port = port, value = value))

    if port not in self.ports:
      raise InvalidResourceError(F('Unhandled port: port={port:W}', port = port))

    if self.ports.index(port) == 0:
      # command port

      if value == SimpleVGACommands.RESET:
        self.reset()
        return

      if value == SimpleVGACommands.REFRESH:
        self.master.refresh_task.on_tick(None)
        return

      self.state = value

    else:
      # data port

      if self.state == SimpleVGACommands.MEMORY_BANK_ID:
        if not 0 <= value < self.memory_banks:
          raise InvalidResourceError(F('Memory bank out of range: bank={bank:d}', bank = value))

        self.active_bank = value
        self.state = None

      else:
        raise InvalidResourceError(F('Invalid internal state: state={state}', state = self.state))
