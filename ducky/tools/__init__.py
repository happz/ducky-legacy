import argparse
import logging
import optparse
import sys

from ..log import create_logger, StreamHandler, LogFormatter, ColorizedLogFormatter

def setup_logger(stream = None, debug = False, quiet = None, verbose = None, default_loglevel = logging.INFO, colorize = None):
  stream = stream or sys.stdout

  if colorize is None:
    colorize = sys.stdout.isatty()

  formatter = ColorizedLogFormatter() if colorize is True else LogFormatter()
  handler = StreamHandler(stream = stream, formatter = formatter)
  logger = create_logger(handler = handler)

  logger.setLevel(logging.INFO)

  if debug:
    logger.setLevel(logging.DEBUG)

  else:
    levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
    quiet = quiet or 0
    verbose = verbose or 0

    level = levels.index(default_loglevel) + quiet - verbose
    level = max(0, level)
    level = min(4, level)

    logger.setLevel(levels[level])

  return logger

def add_common_options(parser):
  group = optparse.OptionGroup(parser, 'Tool verbosity')
  parser.add_option_group(group)

  group.add_option('-d', '--debug', dest = 'debug', action = 'store_true', default = False, help = 'Debug mode')
  group.add_option('-q', '--quiet', dest = 'quiet', action = 'count', default = 0, help = 'Decrease verbosity. This option can be used multiple times')
  group.add_option('-v', '--verbose', dest = 'verbose', action = 'count', default = 0, help = 'Increase verbosity. This option can be used multiple times')

def parse_options(parser, default_loglevel = logging.INFO, stream = None):
  stream = stream or sys.stdout

  if isinstance(parser, argparse.ArgumentParser):
    options = parser.parse_args()
  else:
    options, args = parser.parse_args()

  logger = setup_logger(stream = sys.stdout, debug = options.debug, quiet = options.quiet, verbose = options.verbose, default_loglevel = default_loglevel)

  from signal import signal, SIGPIPE, SIG_DFL
  signal(SIGPIPE, SIG_DFL)

  return options, logger
