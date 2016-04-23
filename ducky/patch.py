import ast
import _ast
import imp
import inspect
import os
import sys

from six import exec_, print_

if os.getenv('VMDEBUG_PATCH', None) == 'yes':
  def debug(s):
    print_('PATCH:', s)

else:
  def debug(s):
    pass

def exec_f(object_, globals_ = None, locals_ = None):
  if not globals_ and not locals_:
    frame = inspect.stack()[1][0]
    globals_ = frame.f_globals
    locals_ = frame.f_locals

  elif globals_ and not locals_:
    locals_ = globals_

  exec_(object_, globals_, locals_)

class RemoveLoggingVisitor(ast.NodeTransformer):
  def visit_Expr(self, node):
    self.generic_visit(node)

    if type(node.value) != ast.Call:
      return node

    if not hasattr(node.value, 'func'):
      return node

    f = node.value.func

    if hasattr(f, "id"):
      if f.id == 'debug':
        debug('removing %s - it is "debug" call' % node)
        return None

      if f.id == 'DEBUG':
        debug('removing %s - it is "DEBUG" call' % node)
        return None

      if f.id == 'log_cpu_core_state':
        debug('removing %s - it is log_cpu_core_state call' % node)
        return None

      if f.id == 'D':
        debug('removing %s - it is D call' % node)
        return None

      return node

    else:
      if hasattr(f, 'attr') and (f.attr == 'DEBUG' or f.attr == 'debug'):
        debug('removing %s - it is DEBUG call' % node)
        return None

    return node

  def visit_If(self, node):
    self.generic_visit(node)

    # if __debug__:
    if isinstance(node.test, _ast.Name) and node.test.id == '__debug__':
      debug('replacing %s - it is __debug__ if' % node)
      debug('  orelse: %s' % node.orelse)

      return node.orelse

    if not node.body:
      debug('removing %s - it is empty if body' % node)
      return None

    return node

  def visit_For(self, node):
    self.generic_visit(node)

    if not node.body:
      debug('removing %s - it is empty for loop' % node)
      return None

    return node

class ModuleLoader(object):
  def __init__(self, fullpath):
    self.fullpath = fullpath

  def get_source(self, path):
    with open(path, 'rb') as f:
      source = f.read()

    return source

  def get_code(self, fullname):
    pkg = self.fullpath.endswith('__init__.py')

    debug('loading module: fullname=%s' % fullname)

    code_str = self.get_source(self.fullpath)
    code_tree = ast.parse(code_str)

    # Modify AST
    if fullname.startswith('ducky'):
      visitor = RemoveLoggingVisitor()
      new_code_tree = visitor.visit(code_tree)

    else:
      new_code_tree = code_tree

    code = compile(new_code_tree, self.fullpath, 'exec')

    return (pkg, code)

  def load_module(self, fullname):
    pkg, code = self.get_code(fullname)

    mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
    mod.__file__ = self.fullpath
    mod.__loader__ = self

    if pkg:
      mod.__path__ = [os.path.dirname(self.fullpath)]

    exec_f(code, mod.__dict__)

    return mod

class Importer(object):
  def find_module(self, fullname, path = None):
    path = path or sys.path

    for directory in path:
      loader = self.loader_for_path(directory, fullname)
      if loader:
        return loader

  def loader_for_path(self, directory, fullname):
    debug('module %s from %s' % (fullname, directory))

    module_path = os.path.join(directory, fullname.split('.')[-1]) + ".py"
    if os.path.exists(module_path):
      loader = ModuleLoader(module_path)
      return loader

    package_path = os.path.join(directory, fullname.split('.')[-1], '__init__.py')
    if os.path.exists(package_path):
      loader = ModuleLoader(package_path)
      return loader

if '-d' not in sys.argv:
  sys.meta_path.insert(0, Importer())
