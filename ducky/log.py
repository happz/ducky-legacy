import colorama
import logging
import tabulate

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
      return '{color_start}[{level}] {msg}{color_stop}'.format(**{
        'color_start': COLORS[record.levelno],
        'color_stop':  COLOR_RESET,
        'level':       LEVELS[record.levelno],
        'msg':         record.getMessage()
      })

    except Exception:
      import sys
      print >> sys.stderr, 'Failure in formatter:'
      print >> sys.stderr, 'record: ' + str(record)
      print >> sys.stderr, 'message: ' + str(record.msg)
      print >> sys.stderr, 'args: ' + str(record.args)
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
