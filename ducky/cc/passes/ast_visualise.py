from . import ASTVisitor

class ASTVisualiseVisitor(ASTVisitor):
  def __init__(self, *args, **kwargs):
    super(ASTVisualiseVisitor, self).__init__(*args, **kwargs)

    self.diag = None
    self.node_indices = []

  def get_index(self, node):
    try:
      return self.node_indices.index(node)

    except ValueError:
      self.node_indices.append(node)
      return self.node_indices.index(node)

  def generic_visit(self, node, shape = 'box'):
    self.diag.append('%i [numbered = %i, label = "%s", shape = %s];' % (self.get_index(node), self.get_index(node), node.__class__.__name__, shape))

    for c_name, c in node.children():
      self.visit(c)
      self.diag.append('%i -> %i [label = "%s"];' % (self.get_index(node), self.get_index(c), c_name))

  def visit_BinaryOp(self, node, shape = 'box'):
    self.diag.append('%i [numbered = %i, label = "BinaryOp\n%s", shape = %s];' % (self.get_index(node), self.get_index(node), node.op, shape))

    self.visit(node.left)
    self.diag.append('%i -> %i;' % (self.get_index(node), self.get_index(node.left)))

    self.visit(node.right)
    self.diag.append('%i -> %i;' % (self.get_index(node), self.get_index(node.right)))

  def visit_Constant(self, node, shape = 'box'):
    self.diag.append('%i [numbered = %i, label = "Constant (%s)", shape = %s];' % (self.get_index(node), self.get_index(node), node.type, shape))

  def visit_ID(self, node, shape = 'box'):
    self.diag.append('%i [numbered = %i, label = "ID\n%s", shape = %s];' % (self.get_index(node), self.get_index(node), node.name, shape))

  def visit_If(self, node):
    self.generic_visit(node, shape = 'diamond')

  def visit_UnaryOp(self, node, shape = 'box'):
    self.diag.append('%i [numbered = %i, label = "UnaryOp\n%s", shape = %s];' % (self.get_index(node), self.get_index(node), node.op, shape))

    self.visit(node.expr)
    self.diag.append('%i -> %i;' % (self.get_index(node), self.get_index(node.expr)))

  def visit_While(self, node):
    self.diag.append('%i [numbered = %i, label = "%s"];' % (self.get_index(node), self.get_index(node), node.__class__.__name__))

    self.visit(node.cond, shape = 'diamond')
    self.diag.append('%i -> %i [label = "cond"];' % (self.get_index(node), self.get_index(node.cond)))

    self.visit(node.stmt)
    self.diag.append('%i -> %i [label = "body"];' % (self.get_index(node), self.get_index(node.stmt)))

  def visit_FileAST(self, node):
    self.DEBUG(self.log_prefix + 'AST visualise pass')
    self.DOWN()

    self.diag = [
      'blockdiag {',
      'orientation = portrait;',
      'node_width = 256;',
      'node_height = 60;',
    ]

    self.generic_visit(node)

    self.diag.append('}')

    with open('ast.diag', 'w') as f:
      f.write('\n'.join(self.diag))

    self.UP()

from . import AST_PASSES
AST_PASSES['ast-visualise'] = ASTVisualiseVisitor
