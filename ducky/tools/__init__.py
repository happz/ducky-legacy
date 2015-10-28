import argparse
import logging
import optparse
import sys

from ..log import create_logger, StreamHandler

def setup_logger(stream = None, debug = False, quiet = False):
  stream = stream or sys.stdout

  logger = create_logger(handler = StreamHandler(stream = stream))
  logger.setLevel(logging.INFO)

  if debug:
    logger.setLevel(logging.DEBUG)

  else:
    levels = [logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

    logger.setLevel(levels[min(quiet, len(levels))])

  return logger

def add_common_options(parser):
  group = optparse.OptionGroup(parser, 'Tool verbosity')
  parser.add_option_group(group)

  group.add_option('-d', '--debug', dest = 'debug', action = 'store_true', default = False, help = 'Debug mode')
  group.add_option('-q', '--quiet', dest = 'quiet', action = 'count', default = 0, help = 'Decrease verbosity. This option can be used multiple times')

def parse_options(parser):
  if isinstance(parser, argparse.ArgumentParser):
    options = parser.parse_args()
  else:
    options, args = parser.parse_args()

  logger = setup_logger(stream = sys.stdout, debug = options.debug, quiet = options.quiet)

  from signal import signal, SIGPIPE, SIG_DFL
  signal(SIGPIPE, SIG_DFL)

  return options, logger
