from pycparser import c_ast

from . import ASTOptVisitor, dump_node

class ConstantFoldingVisitor(ASTOptVisitor):
  priority = 100

  def visit_BinaryOp(self, node):
    self.generic_visit(node)

    L = node.left
    R = node.right

    #
    # If both left and right branches are constants, they can be merged into one
    #
    if isinstance(node.left, c_ast.Constant) and isinstance(node.right, c_ast.Constant):
      self.DEBUG(self.log_prefix + 'Fold: binary op on two constants: %s %s %s', dump_node(self.node_parent), dump_node(node.left), dump_node(node.right))
      self.DOWN()

      if L.type == 'int' and R.type == 'int':
        self.DEBUG(self.log_prefix + 'Fold: both branches are integers, fold into one')

        if node.op == '+':
          i = int(L.value) + int(R.value)

        elif node.op == '*':
          i = int(L.value) * int(R.value)

        else:
          self.WARN(self.log_prefix + '%s: Unhandled binary operation: op=%s', self.__class__.__name__, node.op)

        self.replace_child(node, c_ast.Constant('int', i, coord = node.coord))

        self.UP()

    #
    # Anything multiplied by zero is zero - replace such node with constant
    #
    if node.op == '*' and ((isinstance(L, c_ast.Constant) and L.type == 'int' and L.value == '0') or (isinstance(R, c_ast.Constant) and R.type == 'int' and R.value == '0')):
      self.DEBUG(self.log_prefix + 'Fold: multiply by zero: %s %s %s', dump_node(self.node_parent), dump_node(L), dump_node(R))
      self.DOWN()

      self.replace_child(node, c_ast.Constant('int', 0, coord = node.coord))

      self.UP()

    #
    # Anything multiplied by one keeps its value - discard one branch and replace node with the other
    #
    if node.op == '*' and ((isinstance(L, c_ast.Constant) and L.type == 'int' and L.value == '1') or (isinstance(R, c_ast.Constant) and R.type == 'int' and R.value == '1')):
      self.DEBUG(self.log_prefix + 'Fold: multiply by one: %s %s %s', dump_node(self.node_parent), dump_node(L), dump_node(R))
      self.DOWN()

      keep_node = R if isinstance(L, c_ast.Constant) else L

      self.replace_child(node, keep_node)

      self.UP()

from . import AST_PASSES
AST_PASSES['ast-const-prop'] = ConstantFoldingVisitor
