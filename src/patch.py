import ast
import imp
import os
import re
import sys

def exec_f(object_, globals_ = None, locals_ = None):
  if not globals_ and not locals_:
    frame = inspect.stack()[1][0]
    globals_ = frame.f_globals
    locals_ = frame.f_locals

  elif globals_ and not locals_:
    locals_ = globals_

  exec object_ in globals_, locals_

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
        return None

      if f.id == 'log_cpu_core_state':
        return None

      return node

    else:
      if hasattr(f, 'attr') and f.attr == 'DEBUG':
        return None

    return node

class ModuleLoader(object):
  def __init__(self, fullpath):
    self.fullpath = fullpath
    
  def get_source(self, path):
    with open(path, 'r') as f:
      source = f.read()

    return source
    
  def get_code(self, fullname):
    pkg = self.fullpath.endswith('__init__.py')

    code_str = self.get_source(self.fullpath)
    code_tree = ast.parse(code_str)

    # Modify AST
    visitor = RemoveLoggingVisitor()
    new_code_tree = visitor.visit(code_tree)
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
  def find_module(self, fullname, path = []):
    if not path:
      path = sys.path
        
    for directory in path:
      loader = self.loader_for_path(directory, fullname)
      if loader:
        return loader
    
  def loader_for_path(self, directory, fullname):
    module_path = os.path.join(directory, fullname.split('.')[-1]) + ".py"
    if os.path.exists(module_path):
      loader = ModuleLoader(module_path)
      return loader
        
    package_path = os.path.join(directory, fullname.split('.')[-1], '__init__.py')
    if os.path.exists(package_path):
      loader = ModuleLoader(package_path)
      return loader

if '-d' not in sys.argv:
  sys.meta_path.append(Importer())
