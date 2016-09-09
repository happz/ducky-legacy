import colorama
import logging
import tabulate

from six import print_

LEVELS = {
  logging.DEBUG:    'DEBG',
  logging.INFO:     'INFO',
  logging.WARNING:  'WARN',
  logging.ERROR:    'ERRR',
  logging.CRITICAL: 'CRIT'
}

COLORS = {
  logging.DEBUG:    colorama.Fore.WHITE,
  logging.INFO:     colorama.Fore.GREEN,
  logging.WARNING:  colorama.Fore.YELLOW,
  logging.ERROR:    colorama.Fore.RED,
  logging.CRITICAL: colorama.Fore.RED
}

COLOR_RESET = colorama.Fore.RESET + colorama.Back.RESET + colorama.Style.RESET_ALL

class LogFormatter(logging.Formatter):
  _default_format = '{stamp:.02f} [{level}] {message}'

  def __init__(self, format = None):
    super(LogFormatter, self).__init__()

    self._format = format or self._default_format

  def double_fault(self, exc, record):
    import sys
    import traceback

    print_('Failure in formatter:', file = sys.stderr)
    print_('record: ' + str(record), file = sys.stderr)
    print_('message: ' + str(record.msg), file = sys.stderr)
    print_('args: ' + str(record.args), file = sys.stderr)

    traceback.print_exc(file = sys.stderr)
    sys.exit(1)

  def _get_vars(self, record):
    return {
      'level':       LEVELS[record.levelno],
      'stamp':       record.created
    }

  def format(self, record):
    try:
      vars = self._get_vars(record)

      msg = [self._format.format(message = record.getMessage(), **vars)]

      if record.exc_info is not None:
        msg += [self._format.format(message = l, **vars) for l in self.formatException(record.exc_info).split('\n')]

      return '\n'.join(msg)

    except Exception as e:
      self.double_fault(e, record)

  def colorize(self, s, *args, **kwargs):
    return s

  def red(self, s):
    return s

  def green(self, s):
    return s

  def blue(self, s):
    return s

  def white(self, s):
    return s

class ColorizedLogFormatter(LogFormatter):
  _default_format = '{color_start}{stamp:.02f} [{level}]{color_end} {message}'

  def _get_vars(self, record):
    vars = super(ColorizedLogFormatter, self)._get_vars(record)

    vars.update({
      'color_start': COLORS[record.levelno],
      'color_end':   COLOR_RESET
    })

    return vars

  def colorize(self, s, fore = COLOR_RESET, back = COLOR_RESET):
    return fore + s + back

  def red(self, s):
    return self.colorize(s, fore = colorama.Fore.RED)

  def green(self, s):
    return self.colorize(s, fore = colorama.Fore.GREEN)

  def blue(self, s):
    return self.colorize(s, fore = colorama.Fore.BLUE)

  def white(self, s):
    return self.colorize(s, fore = colorama.Fore.WHITE)

class StreamHandler(logging.StreamHandler):
  def __init__(self, formatter = None, *args, **kwargs):
    super(StreamHandler, self).__init__(*args, **kwargs)

    formatter = formatter or ColorizedLogFormatter()

    self.setFormatter(formatter)

def create_logger(name = None, handler = None, level = logging.INFO):
  name = name or 'ducky'

  logger = logging.getLogger(name)
  if handler:
    logger.addHandler(handler)

  def __table(table, fn = None, **kwargs):
    fn = fn or logger.info

    for line in tabulate.tabulate(table, headers = 'firstrow', tablefmt = 'simple', numalign = 'right', **kwargs).split('\n'):
      fn(line)

  logger.table = __table

  logger.setLevel(level)

  return logger
