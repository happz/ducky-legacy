import colorama
import threading
import enum
import tabulate

CONSOLE_ID = 0

class VerbosityLevels(enum.IntEnum):
  QUIET   = 0
  ERROR   = 1
  WARNING = 2
  INFO    = 3
  DEBUG   = 4

LEVELS = [
  '',
  'ERRR',
  'WARN',
  'INFO',
  'DEBG'
]

COLORS = [
  None,
  colorama.Fore.RED,
  colorama.Fore.YELLOW,
  colorama.Fore.GREEN,
  colorama.Fore.WHITE
]

class Console(object):
  console_id = 0
  commands = {}

  def __init__(self, machine, f_in, f_out):
    super(Console, self).__init__()

    self.machine = machine

    self.f_in = f_in
    self.f_out = f_out

    self.verbosity = VerbosityLevels.ERROR

    self.lock = threading.Lock()

    self.new_line_event = threading.Event()

    self.keep_running = True
    self.thread = None

  @classmethod
  def register_command(cls, name, callback, *args, **kwargs):
    cls.commands[name] = (callback, args, kwargs)

  @classmethod
  def unregister_command(cls, name):
    if name in cls.commands:
      del cls.commands[name]

  def set_verbosity(self, level):
    self.verbosity = level + 1

  def wait_on_line(self):
    self.new_line_event.wait()

  def prompt(self):
    with self.lock:
      self.f_out.write('#> ')
      self.f_out.flush()

  def writeln(self, level, *args):
    if level > self.verbosity:
      return

    with self.lock:
      self.f_out.write('%s[%s] ' % (COLORS[level], LEVELS[level]))
      self.f_out.write('%s' % ' '.join([str(a) for a in args]))
      self.f_out.write(colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL)
      self.f_out.write('\n')
      self.f_out.flush()

  def info(self, *args):
    self.writeln(VerbosityLevels.INFO, *args)

  def debug(self, *args):
    self.writeln(VerbosityLevels.DEBUG, *args)

  def warn(self, *args):
    self.writeln(VerbosityLevels.WARNING, *args)

  def error(self, *args):
    self.writeln(VerbosityLevels.ERROR, *args)

  def quiet(self, *args):
    self.writeln(VerbosityLevels.QUIET, *args)

  def execute(self, cmd):
    if cmd[0] not in self.commands:
      from util import error

      error('Unknown command: %s' % cmd)
      return

    cmd_desc = self.commands[cmd[0]]

    try:
      cmd_desc[0](self, cmd, *cmd_desc[1], **cmd_desc[2])

    except Exception, e:
      import traceback

      s = traceback.format_exc()

      for line in s.split('\n'):
        self.error(line)

  def loop(self):
    while self.keep_running:
      self.new_line_event.clear()

      self.prompt()

      l = self.f_in.readline().strip()
      self.new_line_event.set()

      if not l:
        continue

      cmd = [e.strip() for e in l.split(' ')]

      self.execute(cmd)

  def boot(self):
    self.f_in.flush()
    self.f_out.flush()

    self.boot_thread()

  def halt(self):
    self.keep_running = False

  def boot_thread(self):
    cid = Console.console_id
    Console.console_id += 1

    self.thread = threading.Thread(target = self.loop, name = 'Console #%i' % cid)
    self.thread.daemon = True
    self.thread.start()

def cmd_help(console, cmd):
  """
  List all available command and their descriptions
  """

  table = [
    ['Command', 'Description']
  ]

  for cmd_name in sorted(Console.commands.keys()):
    table.append([cmd_name, Console.commands[cmd_name][0].__doc__])

  from util import print_table
  print_table(table)

def cmd_verbose(console, cmd):
  console.verbosity = min(console.verbosity + 1, VerbosityLevels.DEBUG)
  console.info('New verbosity level is %s' % console.verbosity)

def cmd_quiet(console, cmd):
  console.verbosity = max(console.verbosity - 1, VerbosityLevels.QUIET)
  console.info('New verbosity level is %s' % console.verbosity)

Console.register_command('verbose', cmd_verbose)
Console.register_command('quiet', cmd_quiet)
Console.register_command('?', cmd_help)

