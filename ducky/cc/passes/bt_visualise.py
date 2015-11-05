from six import itervalues

from . import BlockVisitor

class BlockTreeVisualiseVisitor(BlockVisitor):
  priority = 1000

  def __init__(self, *args, **kwargs):
    super(BlockTreeVisualiseVisitor, self).__init__(*args, **kwargs)

    self.diag = None

  def visit(self, cv):
    self.DEBUG(self.log_prefix + 'BT visualise pass')
    self.DOWN()

    self.diag = [
      'blockdiag {',
      'orientation = portrait;',
      'node_width = 256;',
      'node_height = 60;',
    ]

    self.do_visit(cv)

    self.diag.append('}')

    with open('bt.diag', 'w') as f:
      f.write('\n'.join(self.diag))

    self.UP()

  def do_visit_block(self, block):
    name = []

    if block.comment is not None:
      name.append(block.comment)

    if block.names:
      name.append('(%s)' % ', '.join(block.names))

    self.diag.append('%i [numbered = %i, label = "%s"];' % (block.id, block.id, ' '.join(name)))

    if block.outgoing:
      for out_block in itervalues(block.outgoing):
        self.diag.append('%i -> %i;' % (block.id, out_block.id))

from . import BT_PASSES
BT_PASSES['bt-visualise'] = BlockTreeVisualiseVisitor
