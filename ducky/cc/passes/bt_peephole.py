from . import BlockVisitor
from .. import Comment, J, MUL, ADD, LI, STB, LB

class BTPeepholeVisitor(BlockVisitor):
  priority = 100

  def do_visit_block(self, block):
    insts = block.instructions()
    for i in insts:
      if isinstance(i, J):
        index = insts.index(i)

        if index == 0:
          continue

        j = insts[index - 1]

        if not isinstance(j, J):
          continue

        self.DEBUG(self.log_prefix + 'Instruction "%s" follows previous jump instruction "%s", it is effectively dead', i, j)
        block.code[block.code.index(i)] = Comment('instruction "%s" removed by bt-peephole opt pass' % i)
        continue

      if isinstance(i, MUL) and i.operands[1] == 2:
        self.DEBUG(self.log_prefix + 'Instruction "%s" can be replaced by faster one', i)
        block.code[block.code.index(i)] = ADD(i.operands[0], i.operands[0])
        continue

      if isinstance(i, MUL) and i.operands[1] == 1:
        self.DEBUG(self.log_prefix + 'Instruction "%s" is needles, remove', i)
        block.code[block.code.index(i)] = Comment('instruction "%s" removed by bt-peephole opt pass' % i)
        continue

      if isinstance(i, MUL) and i.operands[1] == 0:
        self.DEBUG(self.log_prefix + 'Instruction "%s" can be replaced by faster one', i)
        block.code[block.code.index(i)] = LI(i.operands[0], 0)
        continue

      if isinstance(i, ADD) and i.operands[1] == 0:
        self.DEBUG(self.log_prefix + 'Instruction "%s" is needles, remove', i)
        block.code[block.code.index(i)] = Comment('instruction "%s" removed by bt-peephole opt pass' % i)
        continue

      if isinstance(i, STB):
        index = insts.index(i)

        if index == len(insts) - 1:
          continue

        j = insts[index + 1]

        if not isinstance(j, LB):
          continue

        if i.operands[0] != j.operands[1] or i.operands[1] != j.operands[0]:
          continue

        self.DEBUG(self.log_prefix + 'Instruction "%s" follows "%s", the later is needles. Removing.', j, i)
        block.code[block.code.index(j)] = Comment('instruction "%s" removed by bt-peephole opt pass' % j)
        continue

from . import BT_PASSES
BT_PASSES['bt-peephole'] = BTPeepholeVisitor
