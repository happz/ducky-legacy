import array
import enum
import functools

from ctypes import c_ushort, LittleEndianStructure

from . import Device, IOProvider
from ..errors import InvalidResourceError
from ..mm import UINT16_FMT, ADDR_FMT, PAGE_SIZE, ExternalMemoryPage, addr_to_page, UInt8
from ..util import sizeof_fmt
from ..reactor import RunInIntervalTask

DEFAULT_PORT_RANGE = 0x3F0
DEFAULT_MEMORY_SIZE = 64 * 1024
DEFAULT_MEMORY_BANKS = 8
DEFAULT_MODES = [
  ('g', 320, 200, 1),
  ('t', 80, 25, 2),
  ('t', 80, 25, 1)
]
DEFAULT_BOOT_MODE = ('t', 80, 25, 1)


class SimpleVGACommands(enum.IntEnum):
  RESET          = 0x8001
  REFRESH        = 0x0002

  GRAPHIC        = 0x0020
  COLS           = 0x0021
  ROWS           = 0x0022
  DEPTH          = 0x0023

  MEMORY_BANK_ID = 0x0030


def mode_to_pretty(m):
  return '{type}, {cols}x{rows} {entities}, {memory_per_entity} {memory_label}'.format(**{
    'type': 'text' if m[0] == 't' else 'graphic',
    'cols': m[1],
    'rows': m[2],
    'entities': 'chars' if m[0] == 't' else 'pixels',
    'memory_per_entity': m[3] if m[0] == 't' else m[3] * 8,
    'memory_label': 'bytes per char' if m[0] == 't' else 'bits color depth'
  })

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

  @classmethod
  def from_u8(cls, l, h):
    c = Char()
    c.codepoint = l & 0x7F
    c.fg = h & 0x0F
    c.bg = (h >> 4) & 0x07
    c.blink = h >> 7
    return c

  @classmethod
  def from_u16(cls, u):
    return cls.from_u8(u & 0x00FF, u >> 8)

class DisplayRefreshTask(RunInIntervalTask):
  def __init__(self, display):
    super(DisplayRefreshTask, self).__init__(200, self.on_tick)

    self.display = display
    self.first_tick = True

  def on_tick(self, task):
    self.display.machine.DEBUG('Display: refresh display')

    gpu = self.display.gpu
    mode, cols, rows, depth = gpu.active_mode

    palette_fg = [30, 34, 32, 36, 31, 35, 31, 37,  90,  94,  92,  96,  91,  95, 33,  97]
    palette_bg = [40, 44, 42, 46, 41, 45, 41, 47, 100, 104, 102, 106, 101, 105, 43, 107]

    if mode == 't':
      screen = []

      if depth not in (1, 2):
        self.display.machine.WARN('Unhandled character depth: mode=%s', self.active_mode)
        return

      for row in range(0, rows):
        line = []

        for col in range(0, cols):
          if depth == 1:
            c = Char.from_u8(gpu.memory[row * cols + col], 0)
            c.fg = 15
            c.bg = 0

          else:
            c = Char.from_u8(gpu.memory[(row * cols + col) * 2], gpu.memory[(row * cols + col) * 2 + 1])

          char = '\033[%i;%i;%im%s\033[0m' % (5 if c.blink == 1 else 0, palette_fg[c.fg], palette_bg[c.bg], ' ' if c.codepoint == 0 else chr(c.codepoint))
          line.append(char)

        screen.append(''.join(line))

      if self.first_tick:
        self.first_tick = False
      else:
        print '\033[%iF' % (rows + 3)

      print '-' * cols
      for line in screen:
        print line
      print '-' * cols

    else:
      self.display.machine.WARN('Unhandled gpu mode: mode=%s', gpu.active_mode)

class Display(Device):
  def __init__(self, machine, name, gpu = None, *args, **kwargs):
    super(Display, self).__init__(machine, 'display', name, *args, **kwargs)

    self.gpu = gpu

    self.gpu.set_master(self)

    self.refresh_task = DisplayRefreshTask(self)

  @classmethod
  def get_slave_gpu(cls, machine, config, section):
    gpu_name = config.get(section, 'gpu', None)
    gpu_device = machine.get_device_by_name(gpu_name)

    if not gpu_name or not gpu_device:
      raise InvalidResourceError('Unknown GPU device: gpu=%s', gpu_name)

    return gpu_device

  @classmethod
  def create_from_config(cls, machine, config, section):
    gpu = cls.get_slave_gpu(machine, config, section)

    return Display(machine, section, gpu = gpu)

  def boot(self):
    self.machine.DEBUG('Display.boot')

    super(Display, self).boot()

    self.gpu.boot()
    self.machine.reactor.add_task(self.refresh_task)

    self.machine.INFO('display: generic %s connected to gpu %s', self.name, self.gpu.name)

  def halt(self):
    self.machine.DEBUG('Display.halt')

    super(Display, self).halt()

    self.machine.reactor.remove_task(self.refresh_task)
    self.gpu.halt()

    self.machine.DEBUG('Display: halted')


class SimpleVGAMemoryPage(ExternalMemoryPage):
  def __init__(self, dev, *args, **kwargs):
    super(SimpleVGAMemoryPage, self).__init__(*args, **kwargs)

    self.dev = dev

  def get(self, offset):
    return self.data[self.dev.bank_offsets[self.dev.active_bank] + self.offset + offset]

  def put(self, offset, b):
    self.data[self.dev.bank_offsets[self.dev.active_bank] + self.offset + offset] = b

class SimpleVGA(IOProvider, Device):
  def __init__(self, machine, name, port = None, memory_size = None, memory_address = None, memory_banks = None, modes = None, boot_mode = None, *args, **kwargs):
    if memory_address is None:
      raise InvalidResourceError('sVGA device memory address must be specified explicitly')

    if memory_address % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory address must be page-aligned')

    super(SimpleVGA, self).__init__(machine, 'gpu', name, *args, **kwargs)

    self.port = port or DEFAULT_PORT_RANGE
    self.ports = range(port, port + 2)

    self.memory_size = memory_size or DEFAULT_MEMORY_SIZE
    self.memory_address = memory_address
    self.memory_banks = memory_banks or DEFAULT_MEMORY_BANKS
    self.modes = modes or DEFAULT_MODES

    if self.memory_size % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory size must be page-aligned')

    if (self.memory_size / self.memory_banks) % PAGE_SIZE:
      raise InvalidResourceError('sVGA device memory bank size must be page-aligned')

    self.active_mode = None
    self.boot_mode = boot_mode or DEFAULT_BOOT_MODE

    if self.boot_mode not in self.modes:
      raise InvalidResourceError('Boot mode not available: boot_mode=%s, modes=%s' % (self.boot_mode, self.modes))

    for i, (_, cols, rows, bytes_per_entity) in enumerate(self.modes):
      size = rows * cols * bytes_per_entity
      if size > self.memory_size:
        raise InvalidResourceError('Not enough memory for mode: mode=%s, required=%s bytes, available=%s bytes' % (self.modes[i], size, self.memory_size))

    self.memory = self.data = array.array('B', [0 for _ in range(0, self.memory_size)])
    self.bank_offsets = range(0, self.memory_size, self.memory_size / self.memory_banks)
    self.pages_per_bank = self.memory_size / PAGE_SIZE / self.memory_banks

    self.machine.DEBUG('sVGA: memory-size=%i, memory-banks=%i, offsets=[%s], pages-per-bank=%i, address=%s', self.memory_size, self.memory_banks, ', '.join([ADDR_FMT(o) for o in self.bank_offsets]), self.pages_per_bank, ADDR_FMT(self.memory_address))

  @classmethod
  def create_from_config(cls, machine, config, section):
    _getint = functools.partial(config.getint, section)

    def parse_mode(m):
      t, c, r, b = m.strip().split(',')
      return (t, int(c.strip()), int(r.strip()), int(b.strip()))

    modes = config.get(section, 'modes', None)
    if modes is not None:
      modes = [parse_mode(m) for m in modes.split(';')]

    boot_mode = config.get(section, 'boot-mode', None)
    if boot_mode is not None:
      boot_mode = parse_mode(boot_mode)

    return SimpleVGA(machine, section,
                     port = _getint('port', DEFAULT_PORT_RANGE),
                     memory_size = _getint('memory-size', DEFAULT_MEMORY_SIZE),
                     memory_address = _getint('memory-address', None),
                     memory_banks = _getint('memory-banks', DEFAULT_MEMORY_BANKS),
                     modes = modes,
                     boot_mode = boot_mode)

  def __repr__(self):
    return 'sVGA adapter %s (%s VRAM in %i banks at %s, control [%s]; %s mode)' % (self.name, sizeof_fmt(self.memory_size), self.memory_banks, ADDR_FMT(self.memory_address), ', '.join([UINT16_FMT(port) for port in self.ports]), mode_to_pretty(self.active_mode) if self.active_mode is not None else (mode_to_pretty(self.boot_mode) + ' boot'))

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

    self.machine.INFO('gpu: %s', self)

  def halt(self):
    self.machine.DEBUG('SimpleVGA.halt')

    for pg in self.pages:
      self.machine.memory.unregister_page(pg)

    self.pages = []

    for port in self.ports:
      self.machine.unregister_port(port)

    self.machine.DEBUG('SimpleVGA: halted')

  def read_u16(self, port):
    self.machine.DEBUG('%s.read_u16: port=%s', self.__class__.__name__, UINT16_FMT(port))

    if port != self.ports[1]:
      raise InvalidResourceError('Unable to read from command register')

    if self.state == SimpleVGACommands.GRAPHIC:
      self.state = None
      return 1 if self.active_mode[0] == 'g' else 0

    if self.state == SimpleVGACommands.COLS:
      self.state = None
      return self.active_mode[1]

    if self.state == SimpleVGACommands.ROWS:
      self.state = None
      return self.active_mode[2]

    if self.state == SimpleVGACommands.DEPTH:
      self.state = None
      return self.active_mode[3]

    if self.state == SimpleVGACommands.MEMORY_BANK_ID:
      self.state = None
      return self.active_bank

    raise InvalidResourceError('invalid internal state: state=%s' % UINT16_FMT(self.state))

  def write_u16(self, port, value):
    self.machine.DEBUG('%s.write_u16: port=%s, value=%s', self.__class__.__name__, UINT16_FMT(port), UINT16_FMT(value))

    if port not in self.ports:
      raise InvalidResourceError('Unhandled port: port=%s' % UINT16_FMT(port))

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
        if not (0 <= value < self.memory_banks):
          raise InvalidResourceError('Memory bank out of range: bank=%i' % value)

        self.active_bank = value
        self.state = None

      else:
        raise InvalidResourceError('Invalid internal state: state=%s' % UINT16_FMT(self.state))
