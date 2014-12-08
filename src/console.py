import colorama
import threading
import enum

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
  commands = {}

  def __init__(self, machine, f_in, f_out):
    super(Console, self).__init__()

    self.machine = machine

    self.f_in = f_in
    self.f_out = f_out

    self.verbosity = VerbosityLevels.ERROR

    self.lock = threading.Lock()

    self.keep_running = True
    self.thread = None

  @classmethod
  def register_command(cls, name, callback, *args, **kwargs):
    cls.commands[name] = (callback, args, kwargs)

  def set_verbosity(self, level):
    self.verbosity = level + 1

  def prompt(self):
    with self.lock:
      self.f_out.write('#> ')
      self.f_out.flush()

  def writeln(self, level, *args):
    with self.lock:
      self.f_out.write('%s[%s] ' % (COLORS[level], LEVELS[level]))
      self.f_out.write('%s' % ' '.join([str(a) for a in args]))
      self.f_out.write(colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL)
      self.f_out.write('\n')
      self.f_out.flush()

  def loop(self):
    from util import error

    while self.keep_running:
      self.prompt()

      l = self.f_in.readline().strip()

      if not l:
        continue

      cmd = l.split(' ')[0].strip().lower()

      if cmd not in self.commands:
        error('Unknown command: %s' % l)
        continue

      cmd = self.commands[cmd]
      cmd[0](self, *cmd[1], **cmd[2])

  def boot(self):
    self.f_in.flush()
    self.f_out.flush()

    self.boot_thread()

  def halt(self):
    self.keep_running = False

  def boot_thread(self):
    global CONSOLE_ID

    CONSOLE_ID += 1

    self.thread = threading.Thread(target = self.loop, name = 'Console #%i' % CONSOLE_ID)
    self.thread.daemon = True
    self.thread.start()

def cmd_boot(console):
  console.machine.boot()

def cmd_quit(console):
  from util import info

  info('VM halted by user')

  console.machine.halt()
  console.halt()

def cmd_help(console):
  from util import info

  for cmd_name in Console.commands.keys():
    info(cmd_name)

Console.register_command('quit', cmd_quit)
Console.register_command('boot', cmd_boot)
Console.register_command('help', cmd_help)

