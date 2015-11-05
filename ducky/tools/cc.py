import sys
import argparse

from six import iterkeys

from . import parse_options
from ..cc import CompilerError
from ..cc.passes import AST_PASSES, BT_PASSES

from itertools import chain
from pycparser import parse_file

def compile_file(logger, options, file_in, file_out):
  ast = parse_file(file_in, use_cpp = True, cpp_path = 'gcc', cpp_args = ['-E', r'-Ilibc/include'])

  # ast.show()

  options.passes = list(set(options.passes))

  def __apply_opt_passes(passes, tree):
    tree_modified = True
    while tree_modified is True:
      tree_modified = False

      for opt_pass in iterkeys(passes):
        if opt_pass not in options.passes or ('no-' + opt_pass) in options.passes:
          logger.debug('Pass %s is disabled', opt_pass)
          continue

        logger.debug('Pass %s is enabled, running', opt_pass)

        v = passes[opt_pass](logger)
        v.DOWN()

        v.tree_modified = True
        while v.tree_modified is True:
          v.tree_modified = False
          v.visit(tree)

          if v.tree_modified is True:
            tree_modified = True

        v.UP()

  __apply_opt_passes(AST_PASSES, ast)

  cv = AST_PASSES['ast-codegen'](logger)

  try:
    cv.visit(ast)

  except Exception:
    logger.exception('Exception raised during compilation')
    raise SystemExit(1)

  __apply_opt_passes(BT_PASSES, cv)

  with open(file_out, 'w') as f_out:
    f_out.write(cv.materialize())

def main():
  parser = argparse.ArgumentParser()

  group = parser.add_argument_group('Tool verbosity')
  group.add_argument('-d', '--debug', dest = 'debug', action = 'store_true', default = False, help = 'Debug mode')
  group.add_argument('-q', '--quiet', dest = 'quiet', action = 'count',      default = 0,     help = 'Decrease verbosity. This option can be used multiple times')

  group = parser.add_argument_group('File options')
  group.add_argument('-i', dest = 'file_in',  action = 'append',     default = [],    help = 'Input file')
  group.add_argument('-o', dest = 'file_out', action = 'append',     default = [],    help = 'Output file')
  group.add_argument('-f', dest = 'force',    action = 'store_true', default = False, help = 'Force overwrite of the output file')

  group = parser.add_argument_group('Passes')
  group.add_argument('-O', dest = 'opt_level', action = 'store',      default = 1,     nargs = 1, type = int, help = 'Set requested optimization level', metavar = 'LEVEL')
  group.add_argument('-p', dest = 'passes',    action = 'append',     default = [],    nargs = 1, help = 'Enable or disable optimization pass', metavar = 'PASS')

  options, logger = parse_options(parser)

  from ..cc.passes import load as load_passes
  load_passes(logger)

  options.passes = list(chain.from_iterable(options.passes))

  if options.opt_level == [0]:
    for p in iterkeys(AST_PASSES):
      options.passes.append('no-%s' % p)

    for p in iterkeys(BT_PASSES):
      options.passes.append('no-%s' % p)

  elif options.opt_level == [1]:
    options.passes += ['ast-const-prop', 'ast-dce', 'bt-peephole', 'bt-simplify']

  else:
    pass

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  try:
    for filepath in options.file_in:
      compile_file(logger, options, filepath, options.file_out.pop(0))

  except CompilerError as e:
    logger.error(e.message)
