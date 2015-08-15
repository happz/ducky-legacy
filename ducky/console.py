import tabulate
import types

class ConsoleConnection(object):
  def __init__(self, cid, master, stream):
    super(ConsoleConnection, self).__init__()

    self.cid = cid

    self.master = master
    self.stream = stream

    self.history = []
    self.history_index = 0

    self.buff = []
    self.history.insert(0, self.buff)

    self.default_core = None

  def write(self, buff, *args):
    if isinstance(buff, types.ListType):
      buff = ''.join([chr(c) for c in buff])

    if args:
      buff = buff % args

    self.stream.write(buff)
    self.stream.flush()

  def writeln(self, buff, *args):
    if isinstance(buff, types.ListType):
      buff = ''.join([chr(c) for c in buff])

    self.write(buff + '\n', *args)

  def prompt(self):
    self.write('#> ')

  def table(self, table, **kwargs):
    for line in tabulate.tabulate(table, headers = 'firstrow', tablefmt = 'simple', numalign = 'right', **kwargs).split('\n'):
      self.write(line + '\n')

  def log(self, logger, msg, *args):
    self.writeln(msg, *args)
    logger('[console %i] ' + msg, *((self.cid,) + args))

  def execute(self, cmd):
    if cmd[0] not in self.master.commands:
      self.write('Unknown command: cmd="%s"', cmd)
      return

    cmd_desc = self.master.commands[cmd[0]]

    try:
      cmd_desc[0](self, cmd, *cmd_desc[1], **cmd_desc[2])

    except Exception, exc:
      self.master.machine.EXCEPTION(exc)

  def boot(self):
    self.new_line_event.clear()
    self.prompt()

    self.master.machine.reactor.add_fd(self.stream.fd, on_read = self.read_input, on_error = self.halt)

  def halt(self):
    self.master.machine.reactor.remove_fd(self.stream.fd)
    self.stream.close()

  def die(self, exc):
    self.master.machine.EXCEPTION(exc)
    self.halt()

  def read_input(self):
    def __clear_line():
      self.write([27, 91, 50, 75, 13])

    def __clear_line_from_cursor():
      self.write([27, 91, 75])

    def __move_backward(count = 1):
      self.write([27, 91, count, 68])

    c = ord(self.stream.read(1))

    if c == ord('\n'):
      if self.history_index == 0:
        self.history[0] = ''.join([chr(d) for d in self.buff])

      else:
        self.history.pop(0)
        self.history_index -= 1

      line = self.history[self.history_index]
      self.buff = []

      if not line:
        self.history.pop(0)
        return

      cmd = [e.strip() for e in line.split(' ')]
      self.execute(cmd)
      return

    self.buff.append(c)

    if c == 127:
      self.buff[-1:] = []

      if self.buff:
        self.buff[-1:] = []

        __clear_line()
        self.prompt()
        self.write(self.buff)
        return

    if len(self.buff) >= 3:
      # up arrow
      if self.buff[-3:] == [27, 91, 65]:
        if self.history_index < len(self.history) - 1:
          self.history_index += 1

        self.buff[-3:] = []
        __clear_line()
        self.prompt()
        self.write(self.history[self.history_index])
        return

      # down arrow
      if self.buff[-3:] == [27, 91, 66]:
        if self.history_index > 0:
          self.history_index -= 1

        self.buff[-3:] = []
        __clear_line()
        self.prompt()
        self.write(self.history[self.history_index])
        return

class ConsoleMaster(object):
  console_id = 0

  def __init__(self, machine):
    super(ConsoleMaster, self).__init__()

    self.machine = machine

    self.connections = []
    self.commands = {}

  def register_command(self, name, callback, *args, **kwargs):
    self.commands[name] = (callback, args, kwargs)

  def is_registered_command(self, name):
    return name in self.commands

  def unregister_command(self, name):
    if name in self.commands:
      del self.commands[name]

  def boot(self):
    self.register_command('?', cmd_help)

  def halt(self):
    self.unregister_command('?')

def cmd_help(console, cmd):
  """
  List all available command and their descriptions
  """

  table = [
    ['Command', 'Description']
  ]

  for cmd_name in sorted(console.server.commands.keys()):
    table.append([cmd_name, console.server.commands[cmd_name][0].__doc__])

  console.table(table)
