#! /usr/bin/env python

import sys

from mako.template import Template
from functools import partial

def parse_template(file_in, file_out):
  def _X(i, padding = None):
    padding = ('0' + str(padding)) if padding is not None else ''

    return ('0x%' + padding + 'X') % i

  X = _X
  X2 = partial(_X, padding = 2)
  X4 = partial(_X, padding = 4)
  X8 = partial(_X, padding = 8)

  with open(file_in, 'r') as f_in:
    with open(file_out, 'w') as f_out:
      f_out.write(Template(f_in.read()).render(X = X, X2 = X2, X4 = X4, X8 = X8))

def main():
  import optparse
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  group = optparse.OptionGroup(parser, 'File options')
  parser.add_option_group(group)
  group.add_option('-i', dest = 'file_in', default = None, help = 'Input file')
  group.add_option('-o', dest = 'file_out', default = None, help = 'Output file')
  group.add_option('-f', dest = 'force', default = False, action = 'store_true', help = 'Force overwrite of the output file')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  parse_template(options.file_in, options.file_out)
