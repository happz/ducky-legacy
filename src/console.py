import colorama
import threading
import enum
import select
import tabulate
import traceback
import types

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
    self.logfile = None

    self.verbosity = VerbosityLevels.ERROR

    self.lock = threading.Lock()

    self.new_line_event = threading.Event()

    self.keep_running = True
    self.thread = None

    self.history = []
    self.history_index = 0

  @classmethod
  def register_command(cls, name, callback, *args, **kwargs):
    cls.commands[name] = (callback, args, kwargs)

  @classmethod
  def unregister_command(cls, name):
    if name in cls.commands:
      del cls.commands[name]

  def set_verbosity(self, level):
    self.verbosity = level + 1

  def set_logfile(self, path):
    self.logfile = open(path, 'wb')

  def wait_on_line(self):
    self.new_line_event.wait()

  def prompt(self):
    self.write('#> ')

  def write(self, buff, flush = True):
    if type(buff) == types.ListType:
      buff = ''.join([chr(c) for c in buff])

    with self.lock:
      self.f_out.write(buff)

      if flush:
        self.f_out.flush()

      if self.logfile:
        self.logfile.write(buff)

        if flush:
          self.logfile.flush()

  def writeln(self, level, *args):
    if level > self.verbosity:
      return

    msg = '{color_start}[{level}] {msgs}{color_stop}\n'.format(**{
      'color_start': COLORS[level],
      'color_stop':  colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL,
      'level':       LEVELS[level],
      'msgs':        ' '.join([str(a) for a in args])
    })

    self.write(msg)

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
      self.error('Unknown command: %s' % cmd)
      return

    cmd_desc = self.commands[cmd[0]]

    try:
      cmd_desc[0](self, cmd, *cmd_desc[1], **cmd_desc[2])

    except Exception, e:
      s = traceback.format_exc()

      for line in s.split('\n'):
        self.error(line)

  def loop(self):
    if not self.f_in:
      return

    while self.keep_running:
      self.new_line_event.clear()

      def __clear_line():
        self.write([27, 91, 50, 75, 13])

      def __clear_line_from_cursor():
        self.write([27, 91, 75])

      def __move_backward(count = 1):
        self.write([27, 91, count, 68])

      self.prompt()

      line = None

      buff = []
      self.history.insert(0, buff)
      self.history_index = 0

      while True:
        select.select([self.f_in], [], [])

        c = ord(self.f_in.read(1))

        if c == ord('\n'):
          if self.history_index == 0:
            self.history[0] = ''.join([chr(c) for c in buff])

          else:
            self.history.pop(0)
            self.history_index -= 1

          line = self.history[self.history_index]
          break

        buff.append(c)

        if c == 127:
          buff[-1:] = []

          if len(buff):
            buff[-1:] = []

            __clear_line()
            self.prompt()
            self.write(buff)
            continue

        if len(buff) >= 3:
          # up arrow
          if buff[-3:] == [27, 91, 65]:
            if self.history_index < len(self.history) - 1:
              self.history_index += 1

            buff[-3:] = []
            __clear_line()
            self.prompt()
            self.write(self.history[self.history_index])
            continue

          # down arrow
          if buff[-3:] == [27, 91, 66]:
            if self.history_index > 0:
              self.history_index -= 1

            buff[-3:] = []
            __clear_line()
            self.prompt()
            self.write(self.history[self.history_index])
            continue

      self.new_line_event.set()

      if not line:
        self.history.pop(0)
        continue

      cmd = [e.strip() for e in line.split(' ')]

      self.execute(cmd)

  def boot(self):
    if self.f_in:
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
