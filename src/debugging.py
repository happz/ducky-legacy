from console import Console
from mm import ADDR_FMT

class Point(object):
  point_index = 0
  points = {}

  def __init__(self, debugging_set):
    super(Point, self).__init__()

    self.id = Point.point_index
    Point.point_index += 1
    Point.points[self.id] = self

    self.active = True
    self.flip = True
    self.ephemeral = False
    self.countdown = 0
    self.debugging_set = debugging_set

  def is_triggered(self):
    return False

class WatchPoint(Point):
  def __init__(self, debugging_set, expr):
    super(WatchPoint, self).__init__(debugging_set)

    self.expr = expr

  def is_triggered(self):
    return self.expr(self.debugging_set.owner)

class BreakPoint(WatchPoint):
  def __init__(self, debugging_set, ip):
    super(BreakPoint, self).__init__(debugging_set, lambda core: core.IP().u16 == self.ip)

    self.ip = ip

  def __repr__(self):
    return '<BreakPoint: ip=%s>' % ADDR_FMT(self.ip)

class DebuggingSet(object):
  def __init__(self, owner):
    super(DebuggingSet, self).__init__()

    self.owner = owner

    self.points = {}

  def add_point(self, p):
    self.points[p.id] = p

  def del_point(self, p):
    del self.points[p.id]

  def check(self):
    self.owner.DEBUG('check breakpoints')

    for bp in self.points.values():
      self.owner.DEBUG(str(bp))

      if not bp.active:
        self.owner.DEBUG('inactive, skipping')

        if bp.flip:
          self.owner.DEBUG('point has flip flag set, activate it')
          bp.active = True

        continue

      if not bp.is_triggered():
        self.owner.DEBUG('not triggered, skipping')
        continue

      if bp.countdown:
        bp.countdown -= 1

        if bp.countdown != 0:
          self.owner.DEBUG('countdown %i, skip for now', bp.countdown)
          continue

      self.owner.INFO('Breakpoint triggered: %s', bp)

      bp.active = False

      if bp.ephemeral:
        self.del_point(bp)
        bp.flip = False
        del Point.points[bp.id]

      self.owner.suspend()

def add_breakpoint(core, address, ephemeral = False, countdown = None):
  core.DEBUG('add_breakpoint: address=%s, ephemeral=%s', ADDR_FMT(address), ephemeral)

  p = BreakPoint(core.debug, address)

  if ephemeral:
    p.ephemeral = True

  if countdown:
    p.countdown = int(countdown)

  core.debug.add_point(p)

  return p

def cmd_bp_list(console, cmd):
  """
  List existing breakpoints
  """

  bps = [
    ['ID', 'Active', 'Flip', 'Ephemeral', 'Core', 'Type', 'Address', 'Countdown']
  ]

  for point in Point.points.values():
    bps.append([
      '%i' % point.id,
      '*' if point.active else '',
      '*' if point.flip else '',
      '*' if point.ephemeral else '',
      point.debugging_set.owner.cpuid_prefix,
      str(point.__class__),
      point.ip if isinstance(point, BreakPoint) else '',
      point.countdown
    ])

  from util import print_table
  print_table(bps)

def cmd_bp_add(console, cmd):
  """
  Create new breakpoint: bp_add <#cpuid:#coreid> <address>
  """

  from util import str2int

  core = cmd[1]
  ip = cmd[2]

  core = console.machine.core(cmd[1])
  ip = str2int(ip)

  add_breakpoint(core, ip, ephemeral = 'ephemeral' in cmd)

def cmd_bp_active(console, cmd):
  """
  Tohhle breakpoint "active" flag: bp_active <id>
  """

  point = Point.points[int(cmd[1])]
  point.active = not point.active

Console.register_command('bp_list', cmd_bp_list)
Console.register_command('bp_add', cmd_bp_add)
Console.register_command('bp_active', cmd_bp_active)
