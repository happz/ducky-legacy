from pycparser import c_ast

from . import ASTOptVisitor, dump_node

class DSEVisitor(ASTOptVisitor):
  priority = 500

  def visit_Compound(self, node):
    #
    # Any statement after "return" in a block is effectively dead
    #
    if any([isinstance(stmt, c_ast.Return) for stmt in node.block_items]):
      self.DEBUG(self.log_prefix + 'DCE: Return present in compound block, check for dead statements')
      self.DOWN()

      for stmt in reversed(node.block_items[:]):
        if isinstance(stmt, c_ast.Return):
          break

        self.DEBUG(self.log_prefix + 'removing %s', dump_node(stmt))
        node.block_items.remove(stmt)
        self.tree_modified = True

      self.generic_visit(node)

      self.UP()

from . import AST_PASSES
AST_PASSES['ast-dce'] = DSEVisitor
