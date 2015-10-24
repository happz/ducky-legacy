import os
import sys
import traceback

from pycparser import c_ast

from ..import dump_node, show_node

PASSES = sys.modules[__name__]
PASSES_DIR = os.path.dirname(PASSES.__file__)


AST_PASSES = {}
BT_PASSES  = {}


class ASTVisitor(c_ast.NodeVisitor):
  priority = 99

  def __init__(self, logger, *args, **kwargs):
    super(ASTVisitor, self).__init__(*args, **kwargs)

    self.logger = logger
    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warning
    self.ERROR = logger.error

    self._log_prefix_stack = []
    self.log_prefix = ''

    self.node_parent = None

    self.tree_modified = False

  def UP(self):
    self.log_prefix = (len(self.log_prefix) - 8) * ' '

    if traceback.extract_stack()[-3][2] != self._log_prefix_stack[-1]:
      self.ERROR('whops! tos=%s, current=%s', self._log_prefix_stack[-1], traceback.extract_stack()[-3][2])

    del self._log_prefix_stack[-1]

  def DOWN(self):
    self._log_prefix_stack.append(traceback.extract_stack()[-3][2])
    self.log_prefix += 8 * ' '

  def generic_visit(self, node):
    old_parent = self.node_parent
    self.node_parent = node

    l = [self.visit(c) for c_name, c in node.children()]

    self.node_parent = old_parent

    return l

  def visit(self, node, **kwargs):
    method = 'visit_' + node.__class__.__name__
    visitor = getattr(self, method, self.generic_visit)

    return visitor(node, **kwargs)

class BlockVisitor(object):
  priority = 99

  def __init__(self, logger, *args, **kwargs):
    self.logger = logger
    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warning
    self.ERROR = logger.error

    self.log_prefix = ''

    self.tree_modified = False

  def UP(self):
    self.log_prefix = (len(self.log_prefix) - 8) * ' '

  def DOWN(self):
    self.log_prefix += 8 * ' '

  def do_visit_block(self, block):
    pass

  def visit_block(self, block):
    self.DEBUG(self.log_prefix + 'Examine block %s', block.id)
    self.DOWN()

    self.do_visit_block(block)

    self.UP()

  def do_visit_fn(self, fn):
    for block in fn.blocks:
      self.visit_block(block)

  def visit_fn(self, fn):
    self.DEBUG(self.log_prefix + 'Examine fn %s', fn.name)
    self.DOWN()

    self.do_visit_fn(fn)

    self.UP()

  def do_visit(self, cv):
    for fn in cv.functions:
      self.visit_fn(fn)

  def visit(self, cv):
    self.DEBUG(self.log_prefix + '%s pass', self.__class__.__name__)
    self.DOWN()

    self.do_visit(cv)

    self.UP()

class ASTOptVisitor(ASTVisitor):
  def replace_child(self, current_node, new_node):
    self.DEBUG(self.log_prefix + 'PRE:')
    for line in show_node(self.node_parent).split('\n'):
      self.DEBUG(self.log_prefix + line)

    for name, child in self.node_parent.children():
      if child != current_node:
        continue

      setattr(self.node_parent, name, new_node)
      self.tree_modified = True
      self.DEBUG(self.log_prefix + 'Replaced by %s', dump_node(new_node))
      break

    self.DEBUG(self.log_prefix + 'POST:')
    for line in show_node(self.node_parent).split('\n'):
      self.DEBUG(self.log_prefix + line)

def load(logger):
  passes = {}

  for filename in os.listdir(PASSES_DIR):
    if not filename.endswith(".py") or filename.startswith("_"):
      continue

    if not os.path.isfile(os.path.join(PASSES_DIR, filename)):
      continue

    pass_module = filename[:-3]

    try:
      __import__(PASSES.__name__, {}, {}, [pass_module])
      passes[pass_module] = sys.modules[PASSES.__name__ + '.' + pass_module]
      logger.debug('Pass %s loaded', pass_module)

    except (ImportError, SyntaxError):
      logger.exception('Failed to load pass %s', pass_module)

  return passes
