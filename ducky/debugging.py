"""
Virtual machine debugging tools - break points, watch points, etc.

Create "point" that's triggered when a condition is satisfied (e.g.
processor executes instruction on specified address, memory at
specified address was modified, etc. Then, create "action" (e.g.
suspend core), and bind both pieces together - when point gets
triggered, execute list of actions.
"""

import enum
import logging

from six import itervalues

from .interfaces import IVirtualInterrupt
from .devices import IRQList, VIRTUAL_INTERRUPTS
from .util import str2int, UINT8_FMT, UINT16_FMT, UINT32_FMT
from .errors import InvalidResourceError

class Action(object):
  """
  Base class of all debugging actions.

  :param logging.Logger logger: logger instance used for logging.
  """

  def __init__(self, logger):
    self.logger = logger

  def act(self, core, point):
    """
    This method is called when "action" is executed. Implement it in child
    classes to give child actions a functionality.

    :param ducky.cpu.CPUCore core: CPU core where point was triggered.
    :param ducky.debugging.Point point: point that was triggered.
    """

    raise NotImplementedError()

  def __repr__(self):
    raise NotImplementedError()

class Point(object):
  """
  Base class of all debugging points.

  :param ducky.debugging.DebuggingSet debugging_set: debugging set this point belongs to.
  :param bool active: if not ``True``, point is not active and will not trigger.
  :param int countdown: if greater than zero, point has to trigger ``countdown`` times
    before its actions are executed for the first time.
  """

  def __init__(self, debugging_set, active = True, countdown = 0):
    super(Point, self).__init__()

    self.active = active
    self.countdown = countdown
    self.debugging_set = debugging_set

    self.actions = []

  def is_triggered(self, core, *args, **kwargs):
    """
    Test point's condition.

    :param ducky.cpu.CPUCore core: core requesting the test.
    :rtype: bool
    :returns: ``True`` if condition is satisfied.
    """

    raise NotImplementedError()

  def __repr__(self):
    raise NotImplementedError()

class SuspendCoreAction(Action):
  """
  If executed, this action will suspend the CPU core that triggered its parent
  point.
  """

  def act(self, core, point):
    core.suspend()

  def __repr__(self):
    return '<SuspendCoreAction>'

  @staticmethod
  def create_from_config(debugging_set, config, section):
    return SuspendCoreAction(debugging_set.core.LOGGER)

class LogValueAction(Action):
  """
  This is the base class for actions that log a numerical values.

  :param logging.Logger logger: logger instance used for logging.
  :param int size: size of logged number, in bytes.
  """

  def __init__(self, logger, size):
    super(LogValueAction, self).__init__(logger)

    self.size = size

    if size == 4:
      self.formatter = UINT32_FMT

    elif size == 2:
      self.formatter = UINT16_FMT

    else:
      self.formatter = UINT8_FMT

  def get_values(self, core, point):
    """
    Prepare dictionary with values for message that will be shown to the user.

    :param ducky.cpu.CPUCore core: core point was triggered on.
    :param ducky.debugging.Point point: triggered point.
    :rtype: dict
    :returns: dictionary that will be passed to message ``format()`` method.
    """

    raise NotImplementedError()

  def get_message(self, core, point):
    """
    Return message that, formatted with output of ``get_values()``, will be
    shown to user.

    :param ducky.cpu.CPUCore core: core point was triggered on.
    :param ducky.debugging.Point point: triggered point.
    :rtype: string
    :returns: information message.
    """

    raise NotImplementedError()

  def act(self, core, point):
    data = self.get_values(core, point)
    data.update({
      'watchpoint': repr(point),
      'ip':         UINT32_FMT(core.registers.ip.value),
      'value':      self.formatter(data['value'])
    })

    self.logger.info(self.get_message(core, point).format(**data))

class LogMemoryContentAction(LogValueAction):
  """
  When triggered, logs content of a specified location in memory.

  :param logging.Logger logger: logger instance used for logging.
  :param u32_t address: memory location.
  :param int size: size of logged number, in bytes.
  """

  def __init__(self, logger, address, size):
    super(LogMemoryContentAction, self).__init__(logger, size)

    self.address = address

    if self.size == 4:
      self.reader = 'read_u32'

    elif self.size == 2:
      self.reader = 'read_u16'

    else:
      self.reader = 'read_u8'

  def __repr__(self):
    return '<LogMemoryContentAction: address=%s, size=%s>' % (UINT32_FMT(self.address), self.size)

  def get_values(self, core, point):
    reader = getattr(core.mmu.memory, self.reader)
    return {
      'address': UINT32_FMT(self.address),
      'value':   reader(self.address),
    }

  def get_message(self, core, point):
    return 'memory: IP={ip}, {address}={value}'

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return LogMemoryContentAction(debugging_set.core.LOGGER, _getint('address'), _getint('size', 4))

class LogRegisterContentAction(LogValueAction):
  """
  When triggered, logs content of a specified register.

  :param logging.Logger logger: logger instance used for logging.
  :param list registers: list of register names.
  """

  def __init__(self, logger, registers):
    super(LogRegisterContentAction, self).__init__(logger, 4)

    self.registers = [r.strip() for r in registers.split(',')]
    self.formatter = UINT32_FMT

  def __repr__(self):
    return '<LogRegisterContentAction: registers=%s>' % ','.join(self.registers)

  def get_values(self, core, point):
    values = {'value': 0}
    for r in self.registers:
      values[r] = r
      values[r + '_value'] = UINT32_FMT(getattr(core.registers, r).value)

    return values

  def get_message(self, core, point):
    return 'register: IP={ip}, %s' % ', '.join(['{%s}={%s_value}' % (r, r) for r in self.registers])

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return LogRegisterContentAction(debugging_set.core.LOGGER, _get('registers'))

class BreakPoint(Point):
  def __init__(self, debugging_set, ip, *args, **kwargs):
    super(BreakPoint, self).__init__(debugging_set, *args, **kwargs)

    self.ip = ip

  def is_triggered(self, core):
    core.DEBUG('core IP=%s, self IP=%s', core.IP().value, self.ip)

    return core.IP().value == self.ip

  def __repr__(self):
    return '<BreakPoint: IP=%s>' % UINT32_FMT(self.ip)

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return BreakPoint(debugging_set, _getint('address'), active = _getbool('active', True), countdown = _getint('countdown', 0))

class MemoryWatchPoint(Point):
  def __init__(self, debugging_set, address, read, *args, **kwargs):
    super(MemoryWatchPoint, self).__init__(debugging_set, *args, **kwargs)

    self.address = address
    self.read = read

  def is_triggered(self, core, address = None, read = None):
    core.DEBUG('%s.is_triggered: address=%s, read=%s, self.address=%s, self.read=%s', self.__class__.__name__, UINT32_FMT(address), read, UINT32_FMT(self.address), self.read)

    if self.read is None:
      return address == self.address

    if self.read != read:
      return False

    return address == self.address

  def __repr__(self):
    return '<MemoryWatchPoint: address=%s>' % UINT32_FMT(self.address)

  @staticmethod
  def create_from_config(debugging_set, config, section):
    _get, _getbool, _getint = config.create_getters(section)

    return MemoryWatchPoint(debugging_set, _getint('address'), _getbool('read', None), active = _getbool('active', True), countdown = _getint('countdown', 0))

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

    for chain in ('step', 'memory'):
      setattr(self, 'triggered_%s' % chain, [])

      for stage in ('pre', 'post'):
        setattr(self, 'chain_%s_%s' % (stage, chain), [])

  def add_point(self, p, chain):
    self.core.DEBUG('adding point %s to chain %s', p, chain)

    getattr(self, 'chain_' + chain.replace('-', '_')).append(p)

  def remove_point(self, p, chain):
    self.core.DEBUG('removing point %s from chain %s', p, chain)

    getattr(self, 'chain_' + chain.replace('-', '_')).remove(p)

  def __check_chain(self, stage, chain, clean_triggered = False, *args, **kwargs):
    D = self.core.DEBUG

    D('__check_chain: stage=%s, chain=%s, clean_triggered=%s', stage, chain, clean_triggered)

    triggered = getattr(self, 'triggered_' + chain)
    chain = getattr(self, 'chain_%s_%s' % (stage, chain))

    D('__check_chain: before check: chain=%s, triggered=%s', str(chain), str(triggered))

    triggered_in_loop = 0

    for p in chain:
      D(repr(p))

      if not p.active:
        D('inactive, not evaluating')
        continue

      if not p.is_triggered(self.core, *args, **kwargs):
        D('not triggered, skipping')
        continue

      if p in triggered:
        D('already triggered by this step, ignore')
        continue

      if p.countdown > 0:
        p.countdown -= 1

      if p.countdown != 0:
        D('countdown %i, skip for now', p.countdown)
        continue

      self.core.INFO('Breakpoint triggered: %s', p)
      triggered.append(p)
      triggered_in_loop += 1

      for action in p.actions:
        action.act(self.core, p)

    D('__check_chain: after check: chain=%s, triggered=%s', str(chain), str(triggered))

    if clean_triggered is True:
      triggered[:] = []

    D('__check_chain: after cleanup: chain=%s, triggered=%s', str(chain), str(triggered))

    return triggered_in_loop > 0

  def pre_step(self):
    return self.__check_chain('pre', 'step')

  def post_step(self):
    return self.__check_chain('post', 'step', clean_triggered = True)

  def pre_memory(self, address = None, read = None):
    return self.__check_chain('pre', 'memory', address = address, read = read)

  def post_memory(self, address = None, read = None):
    return self.__check_chain('post', 'memory', clean_triggered = True, address = address, read = read)

def cmd_bp_list(console, cmd):
  """
  List existing breakpoints
  """

  points = [
    ['Point', 'Active', 'Countdown', 'Core']
  ]

  for point in itervalues(Point.points):
    points.append([
      repr(point),
      '*' if point.active else '',
      point.countdown,
      point.debugging_set.core.cpuid_prefix,
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
