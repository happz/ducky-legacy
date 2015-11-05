import enum
import logging

from six import itervalues

from .interfaces import IVirtualInterrupt
from .devices import IRQList, VIRTUAL_INTERRUPTS
from .util import str2int, F
from .errors import InvalidResourceError

class Point(object):
  point_id = 0
  points = {}

  def __init__(self, debugging_set, active = True, countdown = 0):
    super(Point, self).__init__()

    self.id = Point.point_id
    Point.point_id += 1
    Point.points[self.id] = self

    self.active = active
    self.countdown = countdown
    self.debugging_set = debugging_set

  def is_triggered(self, core):
    raise NotImplementedError()

  def destroy(self):
    del Point.points[self.id]

  def __repr__(self):
    return '<%s: id=%i>' % (self.__class__.__name__, self.id)

class BreakPoint(Point):
  def __init__(self, debugging_set, ip, *args, **kwargs):
    super(BreakPoint, self).__init__(debugging_set, *args, **kwargs)

    self.ip = ip

  def is_triggered(self, core):
    core.DEBUG('core IP=%s, self IP=%s', core.IP().value, self.ip)

    return core.IP().value == self.ip

  def __repr__(self):
    return F('<BreakPoint: id={id:d}, ip={ip:W}>', id = self.id, ip = self.ip)

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return BreakPoint(debugging_set, _getint('address'), active = _getbool('active', True), countdown = _getint('countdown', 0))

class MemoryWatchPoint(Point):
  def __init__(self, debugging_set, address, access, *args, **kwargs):
    super(MemoryWatchPoint, self).__init__(debugging_set, *args, **kwargs)

    self.address = address
    self.access = access

  def is_triggered(self, core):
    return False

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return MemoryWatchPoint(debugging_set, _getint('address'), _get('access'), active = _getbool('active', True), countdown = _getint('countdown', 0))

class DebuggingSet(object):
  def __init__(self, core):
    super(DebuggingSet, self).__init__()

    self.core = core
    self.points = []

    self.triggered_points = []

    C = core.cpu.machine.console

    console_commands = [
      ('bp-list', cmd_bp_list),
      ('bp-break', cmd_bp_add_breakpoint),
      ('bp-mwatch', cmd_bp_add_memory_watchpoint),
      ('bp-active', cmd_bp_active)
    ]

    for name, handler in console_commands:
      if C.is_registered_command(name):
        continue

      C.register_command(name, handler)

  def add_point(self, p):
    self.points.append(p)

  def remove_point(self, p):
    self.points.remove(p)
    p.destroy()

  def enter_step(self):
    D = self.core.DEBUG

    D('check breakpoints')

    for p in self.points:
      D(repr(p))

      if not p.active:
        D('inactive, not evaluating')
        continue

      if not p.is_triggered(self.core):
        D('not triggered, skipping')
        continue

      if p in self.triggered_points:
        D('already triggered by this step, ignore')
        continue

      if p.countdown > 0:
        p.countdown -= 1

      if p.countdown != 0:
        D('countdown %i, skip for now', p.countdown)
        continue

      self.core.INFO('Breakpoint triggered: %s', p)
      self.triggered_points.append(p)
      self.core.suspend()

      return True

    return False

  def exit_step(self):
    self.triggered_points = []

  def create_point(self, klass, *args, **kwargs):
    self.core.init_debug_set()

    p = klass(self, *args, **kwargs)
    self.add_point(p)

    return p

def cmd_bp_list(console, cmd):
  """
  List existing breakpoints
  """

  points = [
    ['ID', 'Active', 'Countdown', 'Core', 'Point']
  ]

  for point in itervalues(Point.points):
    points.append([
      point.id,
      '*' if point.active else '',
      point.countdown,
      point.debugging_set.core.cpuid_prefix,
      repr(point)
    ])

  console.table(points)

def cmd_bp_add_breakpoint(console, cmd):
  """
  Create new breakpoint: bp-break <#cpuid:#coreid> <address> [active] [countdown]
  """

  try:
    core = console.master.machine.core(cmd[1])

  except InvalidResourceError:
    console.write('go away')
    return

  ip = str2int(cmd[2])
  active = True if len(cmd) >= 3 and cmd[2] == 'yes' else False
  countdown = str2int(cmd[3]) if len(cmd) >= 4 else 0

  core.init_debug_set()
  point = core.debug.create_point(BreakPoint, ip, active = active, countdown = countdown)

  console.writeln('# OK: %s', point)

def cmd_bp_add_memory_watchpoint(console, cmd):
  """
  Create new memory watchpoint: bp-mwatch <#cpuid:#coreid> <address> [rw] [active] [countdown]'
  """

  try:
    core = console.master.machine.core(cmd[1])

  except InvalidResourceError:
    console.write('go away')
    return

  address = str2int(cmd[2])
  access = cmd[3] if len(cmd) >= 4 else 'r'
  active = True if len(cmd) >= 5 and cmd[4] == 'yes' else False
  countdown = str2int(cmd[5]) if len(cmd) >= 6 else 0

  core.init_debug_set()
  point = core.debug.create_point(MemoryWatchPoint, address, access, active = active, countdown = countdown)

  console.writeln('# OK: %s', point)

def cmd_bp_remove(console, cmd):
  """
  Remove breakpoint: bp-remove <id>
  """

  point = Point.points.get(int(cmd[1]))
  if point is None:
    console.writeln('go away')
    return

  point.debugging_set.remove_point(point)

  console.writeln('# OK')

def cmd_bp_active(console, cmd):
  """
  Toggle "active" flag for a breakpoint: bp-active <id>
  """

  point = Point.points.get(int(cmd[1]))
  if point is None:
    console.writeln('go away')
    return

  point.active = not point.active

  console.writeln('# OK: %s', point)

class VMDebugOperationList(enum.Enum):
  LOGGER_VERBOSITY = 0

class VMVerbosityLevels(enum.Enum):
  DEBUG = 0
  INFO = 1
  WARNING = 2
  ERROR = 3

VERBOSITY_LEVEL_MAP = {
  VMVerbosityLevels.DEBUG.value:   logging.DEBUG,
  VMVerbosityLevels.INFO.value:    logging.INFO,
  VMVerbosityLevels.WARNING.value: logging.WARNING,
  VMVerbosityLevels.ERROR.value:   logging.ERROR
}

class VMDebugInterrupt(IVirtualInterrupt):
  def run(self, core):
    from .cpu.registers import Registers

    core.DEBUG('VMDebugInterrupt: triggered')

    op = core.REG(Registers.R00).value
    core.REG(Registers.R00).value = 0xFFFF

    if op == VMDebugOperationList.LOGGER_VERBOSITY.value:
      verbosity = core.REG(Registers.R01).value

      if verbosity not in VERBOSITY_LEVEL_MAP:
        core.WARN('VMDebugInterrupt: unknown verbosity level: %s', verbosity)
        return

      core.LOGGER.setLevel(VERBOSITY_LEVEL_MAP[verbosity])
      core.DEBUG('VMDebugInterrupt: setting verbosity to %s', verbosity)

    else:
      core.WARN('VMDebugInterrupt: unknown operation requested: %s', op)

VIRTUAL_INTERRUPTS[IRQList.VMDEBUG.value] = VMDebugInterrupt
