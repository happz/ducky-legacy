#! /usr/bin/env python

import sys

from six import print_
from mako.template import Template
from functools import partial

if len(sys.argv) != 2:
  print_('Usage: template.py <source file>')
  sys.exit(1)


def _X(i, padding = None):
  padding = ('0' + str(padding)) if padding is not None else ''

  return ('0x%' + padding + 'X') % i

X = _X
X2 = partial(_X, padding = 2)
X4 = partial(_X, padding = 4)
X8 = partial(_X, padding = 8)

with open(sys.argv[1], 'r') as f:
  print_(Template(f.read()).render(X = X, X2 = X2, X4 = X4, X8 = X8))
