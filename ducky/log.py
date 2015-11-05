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

def RED(s):
  return colorama.Fore.RED + s + COLOR_RESET

def GREEN(s):
  return colorama.Fore.GREEN + s + COLOR_RESET

def BLUE(s):
  return colorama.Fore.BLUE + s + COLOR_RESET

def WHITE(s):
  return colorama.Fore.WHITE + s + COLOR_RESET

class LogFormatter(logging.Formatter):
  def format(self, record):
    try:
      prefix = '{color_start}{stamp:.02f} [{level}] '.format(color_start = COLORS[record.levelno], level = LEVELS[record.levelno], stamp = record.created)
      postfix = COLOR_RESET

      msg = [prefix + record.getMessage() + postfix]

      if record.exc_info is not None:
        msg += [prefix + l + postfix for l in self.formatException(record.exc_info).split('\n')[-9:]]

      return '\n'.join(msg)

    except Exception:
      import sys
      import traceback
      print_('Failure in formatter:', file = sys.stderr)
      print_('record: ' + str(record), file = sys.stderr)
      print_('message: ' + str(record.msg), file = sys.stderr)
      print_('args: ' + str(record.args), file = sys.stderr)
      traceback.print_exc(file = sys.stderr)
      sys.exit(1)

class StreamHandler(logging.StreamHandler):
  def __init__(self, *args, **kwargs):
    super(StreamHandler, self).__init__(*args, **kwargs)

    self.setFormatter(LogFormatter())

def create_logger(name = None, handler = None):
  name = name or 'ducky'

  logger = logging.getLogger(name)
  if handler:
    logger.addHandler(handler)

  def __table(table, fn = None, **kwargs):
    fn = fn or logger.info

    for line in tabulate.tabulate(table, headers = 'firstrow', tablefmt = 'simple', numalign = 'right', **kwargs).split('\n'):
      fn(line)

  logger.table = __table

  return logger
