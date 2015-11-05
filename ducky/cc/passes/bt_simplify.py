from six import itervalues

from . import BlockVisitor
from .. import J

class BlockTreeSimplifyVisitor(BlockVisitor):
  priority = 500

  def do_visit_fn(self, fn):
    # Remove empty blocks
    for block in fn.blocks[:]:
      # self.DEBUG(self.log_prefix + 'Block: %s', block)
      # self.DEBUG(self.log_prefix + '  Code: %s, Instr: %s', block.code, block.instructions())

      if block.instructions():
        continue

      if block.names:
        # If it has no outgoing block, it weird but let not mess with it right now
        # if it has multiple outgoing blocks, lets not mess with this one
        if len(block.outgoing) != 1:
          continue

        next_block = list(block.outgoing.values())[0]

        self.DEBUG(self.log_prefix + 'Block %s is empty, but is named - merging its names to the following block %s', block, next_block)

        # Merge names to the following block
        next_block.names += block.names
        block.names = []

      if block.names or len(block.outgoing) > 1:
        continue

      fn.blocks.remove(block)

      out_block = list(block.outgoing.values())[0] if block.outgoing else None
      if out_block is not None:
        del out_block.incoming[block.id]

      for in_block in itervalues(block.incoming):
        del in_block.outgoing[block.id]
        if out_block is not None:
          in_block.add_outgoing(out_block)
          out_block.add_incoming(in_block)

      self.DEBUG(self.log_prefix + 'Block %s is empty, removed', block)

    # Get rid of "jump-to-directly-next-block" instructions
    prev = None
    for block in fn.blocks:
      if prev is None or not prev.code or not isinstance(prev.instructions()[-1], J) or prev.instructions()[-1].operands[0] not in ['&%s' % name for name in block.names]:
        prev = block
        continue

      prev.code.remove(prev.instructions()[-1])
      self.DEBUG(self.log_prefix + 'Block %s jumps directly to next block %s', prev, block)

      prev = block

from . import BT_PASSES
BT_PASSES['bt-simplify'] = BlockTreeSimplifyVisitor
