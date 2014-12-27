import threading
import tabulate

from mm import ADDR_FMT
from cpu.errors import CPUException

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

    self.points = []

  def check(self):
    from util import debug, info

    debug(self.owner.cpuid_prefix, 'check breakpoints')

    for bp in self.points:
      debug(self.owner.cpuid_prefix, bp)

      if not bp.active:
        debug(self.owner.cpuid_prefix, 'inactive, skipping')

        if bp.flip:
          debug(self.owner.cpuid_prefix, 'point has flip flag set, activate it')
          bp.active = True

        continue

      if not bp.is_triggered():
        debug(self.owner.cpuid_prefix, 'not triggered, skipping')
        continue

      info(self.owner.cpuid_prefix, 'Breakpoint triggered: %s' % bp)

      bp.active = False
      bp.flip = True

      event = threading.Event()
      event.clear()
      self.owner.plan_suspend(event)

def get_core_by_id(machine, cid):
  # cid has format '#cpuid:#coreid'

  cid = cid.split(':')
  return machine.cpus[int(cid[0][1:])].cores[int(cid[1][1:])]

def cmd_bp_list(console, cmd):
  """
  List existing breakpoints
  """

  bps = [
    ['ID', 'Active', 'Flip', 'Core', 'Type', 'Address']
  ]

  for point in Point.points.values():
    bps.append([
      '%i' % point.id,
      '*' if point.active else '',
      '*' if point.flip else '',
      point.debugging_set.owner.cpuid_prefix,
      str(point.__class__),
      point.ip if isinstance(point, BreakPoint) else ''
    ])

  from util import print_table
  print_table(bps)

def cmd_bp_add(console, cmd):
  """
  Create new breakpoint: bp_add <#cpuid:#coreid> <address>
  """

  core = cmd[1]
  ip = cmd[2]

  core = get_core_by_id(console.machine, cmd[1])

  ip = int(ip, base = 16) if ip.startswith('0x') else int(ip)
    
  bp = BreakPoint(core.debug, ip)
  core.debug.points.append(bp)

  from util import info
  info('New breakpoint set, it\'s id is %i' % bp.id)

def cmd_bp_active(console, cmd):
  """
  Tohhle breakpoint "active" flag: bp_active <id>
  """

  point = Point.points[int(cmd[1])]
  point.active = not point.active

import console
console.Console.register_command('bp_list', cmd_bp_list)
console.Console.register_command('bp_add', cmd_bp_add)
console.Console.register_command('bp_active', cmd_bp_active)

