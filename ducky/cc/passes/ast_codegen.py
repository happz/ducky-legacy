from pycparser import c_ast

from six import iteritems, iterkeys

from . import ASTVisitor
from .. import *
from ..types import *

class CodegenVisitor(ASTVisitor):
  priority = 1000

  def __init__(self, *args, **kwargs):
    super(CodegenVisitor, self).__init__(*args, **kwargs)

    self.types = {
      'void':          VoidType(self),
      'int':           IntType(self),
      'unsigned int':  UnsignedIntType(self),
      'char':          CharType(self),
      'unsigned char': UnsignedCharType(self)
    }
    self.types['unsigned'] = self.types['unsigned int']

    for desc in list(iterkeys(self.types)):
      self.types[desc + ' *'] = PointerType(self.types[desc], self)

    self.functions = []
    self.global_scope = Scope(self)

    self.FN       = None
    self.BLOCK    = None
    self.SCOPE    = self.global_scope
    self.EMIT     = None
    self.GET_REG  = None
    self.REGS     = None

    self.blocks = []
    self.prolog_blocks = []
    self.epilog_blocks = []

    self.label_index = 0
    self.literal_label_index = 0
    self.string_literals = {}

    self.break_stack = []
    self.continue_stack = []

    self.make_current(self.block(name = self.get_new_label(name = 'global')))

  def block(self, stage = None, *args, **kwargs):
    block = Block(*args, **kwargs)

    if stage == 'prolog':
      self.prolog_blocks.append(block)

    elif stage == 'epilog':
      self.epilog_blocks.append(block)

    else:
      self.blocks.append(block)

    return block

  def make_current(self, block):
    self.DEBUG(self.log_prefix + 'new current block: %s', block)

    self.BLOCK = block
    self.EMIT = block.emit

  def reset_scope(self):
    while self.SCOPE != self.global_scope:
      self.pop_scope()

  def push_scope(self):
    self.SCOPE = Scope(self, parent = self.SCOPE)

    self.DEBUG(self.log_prefix + 'scope: pushing new scope: scope=%s, parent=%s', self.SCOPE, self.SCOPE.parent)

    return self.SCOPE

  def pop_scope(self):
    self.DEBUG(self.log_prefix + 'scope: popping scope: scope=%s, parent=%s', self.SCOPE, self.SCOPE.parent)

    self.SCOPE = self.SCOPE.parent

  def get_new_label(self, name = None):
    self.label_index += 1
    return '.L%i' % self.label_index if name is None else '.L%i_%s' % (self.label_index, name)

  def get_new_literal_label(self):
    self.literal_label_index += 1
    return '.LC%i' % self.literal_label_index

  def get_new_local_storage(self, size):
    assert self.FN is not None

    self.FN.fp_offset -= size
    if self.FN.fp_offset % 2:
      self.FN.fp_offset -= 1

    return StackSlotStorage(None, self.FN.fp_offset)

  def emit_string_literals(self):
    B = self.block(stage = 'prolog', comment = 'global prolog')

    B.emit(Directive('.include "defs.asm"'))
    B.emit(Directive('.section .rodata'))

    for label, s in iteritems(self.string_literals):
      B.emit(Directive('.type %s, string' % label))
      B.emit(Directive('.string %s' % s))

  def emit_trampoline(self):
    trampoline = self.block(stage = 'epilog', name = '_start', comment = 'global epilog')

    trampoline.emit(CALL('&main'))
    trampoline.emit(INT('$INT_HALT'))
    trampoline.emit(Directive('.global _start'))

  def emit_prolog(self):
    self.emit_string_literals()

  def emit_epilog(self):
    self.emit_trampoline()

  def materialize(self):
    # Emit translation unit prolog and epilog
    self.emit_prolog()
    self.emit_epilog()

    # Now materialize block tree
    code = []

    for block in self.prolog_blocks:
      block.materialize(code)
      code.append('')

    for block in self.blocks:
      block.materialize(code)
      code.append('')

    for fn in self.functions:
      code += fn.materialize()
      code.append('')

    for block in self.epilog_blocks:
      block.materialize(code)
      code.append('')

    return '\n'.join(code)

  def visit(self, node, **kwargs):
    method = 'visit_' + node.__class__.__name__
    visitor = getattr(self, method, self.generic_visit)

    if visitor == self.generic_visit:
      self.WARN(self.log_prefix + 'Unhandled node class: %s', node.__class__.__name__)

    return visitor(node, **kwargs)

  def generic_visit(self, node, **kwargs):
    old_parent = self.node_parent
    self.node_parent = node

    ret = []
    for c_name, c in node.children():
      ret.append(self.visit(c, **kwargs))

    self.node_parent = old_parent

    return ret

  def visit_constant_value(self, node):
    self.DEBUG(self.log_prefix + 'visit_constant_value: %s', dump_node(node))

    if node.type == 'string':
      label = self.get_new_literal_label()
      self.string_literals[label] = node.value

      return RValueExpression(value = ConstantValue('&%s' % label), type = CType.get_from_desc(self, 'char *'))

    if node.type == 'int':
      return RValueExpression(value = ConstantValue(node.value), type = CType.get_from_desc(self, 'int'))

    if node.type == 'char':
      special_chars = [r'\0']

      c = node.value[1:-1]
      if c in special_chars:
        return RValueExpression(value = ConstantValue(str(special_chars.index(c))), type = CType.get_from_desc(self, 'char'))

      return RValueExpression(value = ConstantValue(str(ord(c))), type = CType.get_from_desc(self, 'char'))

    raise CompilerError(node.coord, 'Unhandled branch: Constant, type=%s' % node.type)

  def visit_expr(self, node, preferred = None, keep = None):
    self.DEBUG(self.log_prefix + 'visit_expr: node=%s, preferred=%s, keep=%s', dump_node(node), preferred, keep)
    self.DOWN()

    E = self.visit(node, preferred = preferred, keep = keep)
    self.DEBUG(self.log_prefix + 'visit_expr: expr=%s', E)

    self.UP()
    return E

  def process_cond(self, node, iftrue_label = None, iffalse_label = None):
    CE = self.visit(node)
    self.DEBUG(self.log_prefix + 'cond=%s', CE)

    if CE.value is None:
      # check flags according to our cond

      if isinstance(node, c_ast.BinaryOp):
        if iftrue_label is not None:
          if node.op == '==':
            self.EMIT(BE('&' + iftrue_label))

          elif node.op == '!=':
            self.EMIT(BNE('&' + iftrue_label))

          elif node.op == '<=':
            self.EMIT(BLE('&' + iftrue_label))

          elif node.op == '>=':
            self.EMIT(BGE('&' + iftrue_label))

          else:
            self.WARN(self.log_prefix + 'Condition handling not implemented: BinaryOp, op=%s', node.op)

        if iffalse_label is not None:
          if node.op == '==':
            self.EMIT(BNE('&' + iffalse_label))

          elif node.op == '!=':
            self.EMIT(BE('&' + iffalse_label))

          elif node.op == '<=':
            self.EMIT(BG('&' + iffalse_label))

          elif node.op == '>=':
            self.EMIT(BL('&' + iffalse_label))

          else:
            self.WARN(self.log_prefix + 'Condition handling not implemented: BinaryOp, op=%s', node.op)

      else:
        self.WARN(self.log_prefix + 'Condition handling not implemented: cond=%s', dump_node(node))

  def _perform_implicit_conversion(self, loc, E, T):
    self.DEBUG(self.log_prefix + '_perform_implicit_conversion: E=%s, T=%s', E, T)
    self.DOWN()

    assert E.is_rvalue()

    # Any integer type rvalue can be converted to any other integer type, with
    # possible loss of precision.
    if isinstance(E.type, IntType):
      if isinstance(T, UnsignedIntType):
        value = E.value

        if isinstance(value, ConstantValue):
          if int(value.value) < 0:
            value = 2 ^ 16 + int(value.value)

          else:
            value = value.value

          self.UP()
          return RValueExpression(value = ConstantValue(str(value)), type = T), E

        elif isinstance(value, RegisterValue):
          self.UP()
          return RValueExpression(value = value, type = T), E

        else:
          self.WARN(self.log_prefix + 'Unhandled conversion branch')

    if isinstance(E.type, UnsignedIntType):
      if isinstance(T, IntType):
        value = E.value

        if isinstance(value, ConstantValue):
          if int(value.value) >= 32768:
            self.WARN(self.log_prefix + 'Implicit "%s" -> "%s" conversion - value "%s" cannot fit into destination', E.type, T, value.value)

          self.UP()
          return RValueExpression(value = ConstantValue(str(value.value)), type = T), E

        elif isinstance(value, RegisterValue):
          self.UP()
          return RValueExpression(value = value, type = T), E

        else:
          self.WARN(self.log_prefix + 'Unhandled conversion branch')

    if isinstance(E.type, PointerType):
      if isinstance(T, PointerType):
        # void * can be casted to any pointer, and any pointer can be casted to void *
        if isinstance(E.type.ptr_to_type, VoidType) or isinstance(T.ptr_to_type, VoidType):
          self.UP()
          return RValueExpression(value = E.value, type = T), E

    raise IncompatibleTypesError(loc, T, E.type)

  #
  # Real visitors
  #

  def visit_ArrayRef(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    AE = self.visit_expr(node.name)
    self.DEBUG(self.log_prefix + 'array=%s', AE)

    SE = self.visit_expr(node.subscript)
    self.DEBUG(self.log_prefix + 'subscript=%s', SE)

    if not SE.is_rvalue():
      SE, old_SE = SE.to_rvalue(self)
      self.DEBUG(self.log_prefix + 'subscript=%s', SE)

    reg = self.GET_REG(keep = [array_reg, subscript_reg])
    self.EMIT(MOV(reg.name, subscript))
    self.EMIT(MUL(reg.name, len(array_symbol.type.ptr_to_type)))
    self.EMIT(ADD(reg.name, array))

    self.PUT_REG(array_reg)
    self.PUT_REG(subscript_reg)

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return reg.name, reg, array_symbol

  def visit_Assignment(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    LE = self.visit_expr(node.lvalue)
    RE = self.visit_expr(node.rvalue)

    self.DEBUG(self.log_prefix + 'left=%s', LE)
    self.DEBUG(self.log_prefix + 'right=%s', RE)

    if not LE.is_mlvalue():
      raise CompilerError(node.coord, 'Unable to assign to a read-only variable')

    if RE.is_lvalue():
      # Implicit lvalue->rvalue conversion must take a place here
      RE, old_RE = RE.to_rvalue(self)
      self.DEBUG(self.log_prefix + 'right=%s', RE)

    self.DEBUG(self.log_prefix + 'value "%s" to storage "%s", %i bytes', RE.type, LE.type, len(LE.type.ptr_to_type))

    if LE.type.ptr_to_type != RE.type:
      RE, old_RE = self._perform_implicit_conversion(node.coord, RE, LE.type.ptr_to_type)
      self.DEBUG(self.log_prefix + 'right=%s', RE)

    if LE.value.can_register_backed():
      if not LE.value.is_register_backed():
        self.EMIT(Comment('LE can be backed by register, no register acquired yet'))

        if isinstance(RE.value, RegisterValue) and RE.value.register.storage is None:
          LE.value.storage.acquire_register(RE.value.register)
          LE.value.backing_register().dirty = True

        else:
          R = self.GET_REG()
          LE.value.storage.acquire_register(R)
          self.EMIT(MOV(LE.value.backing_register().name, RE.value.name))

      else:
        self.EMIT(MOV(LE.value.backing_register().name, RE.value.name))

      LE.value.backing_register().dirty = True

    else:
      if len(LE.type.ptr_to_type) == 1:
        self.EMIT(STB(LE.value.name, RE.value.name))

      elif len(LE.type.ptr_to_type) == 2:
        self.EMIT(STW(LE.value.name, RE.value.name))

      else:
        self.WARN(self.log_prefix + 'Unhandled assignment size branch')

    if isinstance(LE.value, RegisterValue):
      LE.value.register.put()

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return RE

  def visit_BinaryOp(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + '%s, preferred=%s, keep=%s', dump_node(node), preferred, keep)
    self.DOWN()
    self.EMIT(Comment(dump_node(node)))

    self.EMIT(Comment('left: ' + dump_node(node.left)))
    self.EMIT(Comment('right: ' + dump_node(node.right)))

    LE = self.visit_expr(node.left)
    RE = self.visit_expr(node.right)

    self.DEBUG(self.log_prefix + 'left=%s', LE)
    self.DEBUG(self.log_prefix + 'right=%s', RE)

    if not LE.is_rvalue():
      LE, old_LE = LE.to_rvalue(self)
      self.DEBUG(self.log_prefix + 'left=%s', LE)

    if not RE.is_rvalue():
      RE, old_RE = RE.to_rvalue(self)
      self.DEBUG(self.log_prefix + 'right=%s', RE)

    keep = keep or []

    def __binop_arith(inst):
      E = RValueExpression(value = RegisterValue(self.GET_REG(preferred = preferred, keep = keep + [LE.value, RE.value])), type = LE.type)

      if isinstance(LE.value, RegisterValue):
        self.EMIT(MOV(E.value.name, LE.value.name))

      elif isinstance(LE.value, ConstantValue):
        self.EMIT(LI(E.value.name, LE.value.name))

      else:
        self.WARN(self.log_prefix + 'Unhandled binop arith branch')

      self.EMIT(inst(E.value.name, RE.value.name))

      return E

    if LE.type != RE.type:
      RE, old_RE = self._perform_implicit_conversion(node.coord, RE, LE.type)
      self.DEBUG(self.log_prefix + 'right=%s', RE)

    R = None

    if node.op == '+':
      R = __binop_arith(ADD)

    elif node.op == '-':
      R = __binop_arith(SUB)

    elif node.op == '*':
      ret, ret_reg = __binop_arith(MUL)

    elif node.op == '&':
      R = __binop_arith(AND)

    elif node.op == '||':
      R = __binop_arith(OR)

    elif node.op in ('!=', '>=', '<=', '==', '>', '<'):
      R = RValueExpression(type = IntType(self))

      self.EMIT(CMP(LE.value.name, RE.value.name))

    else:
      self.WARN(self.log_prefix + 'Unhandled binary op: op=%s', node.op)

    if isinstance(LE.value, RegisterValue):
      LE.value.register.put()
    if isinstance(RE.value, RegisterValue):
      RE.value.register.put()

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return R

  def visit_Cast(self, node, **kwargs):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    E = self.visit_expr(node.expr, **kwargs)
    self.DEBUG(self.log_prefix + 'expr=%s', E)

    if E.is_lvalue():
      E, old_E = E.to_rvalue(self)
      self.DEBUG(self.log_prefix + 'expr=%s', E)

    self.DEBUG(self.log_prefix + 'typename: %s', dump_node(node.to_type))
    T = CType.get_from_decl(self, node.to_type.type)
    self.DEBUG(self.log_prefix + 'type: %s', T)

    R = RValueExpression(value = RegisterValue(self.GET_REG(**kwargs)), type = T)

    self.EMIT(Comment('casting %s to %s' % (E, T)))
    self.EMIT(MOV(R.value.name, E.value.name))

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return R

  def visit_Compound(self, node, create_scope = True):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    self.EMIT(Comment(dump_node(node)))

    if create_scope:
      self.push_scope()

    ret = self.generic_visit(node)
    self.DEBUG(self.log_prefix + 'compound output: %s', ret)

    for r in ret:
      if r is None or not isinstance(r.value, RegisterValue):
        continue

      r.value.register.put()

    self.pop_scope()
    self.UP()

  def visit_Constant(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.DEBUG(self.log_prefix + '%s: preferred=%s, keep=%s', comment, preferred, keep)
    self.DOWN()
    self.EMIT(Comment(comment))

    E = self.visit_constant_value(node)

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return E

  def visit_Decl(self, node):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    if node.name is None:  # declaring a type, structure probably... we'll see
      T = CType.create_from_decl(self, node)
      self.types[repr(T)] = T

      # self.EMIT(Comment('/ ' + comment))
      self.UP()
      return T

    symbol = self.SCOPE.add(node.coord, Symbol(self, node.name, CType.create_from_decl(self, node.type), extern = ('extern' in node.storage), const = ('const' in node.quals)))

    RE_class = MLValueExpression if 'const' in node.quals else LValueExpression
    RE = RE_class(type = PointerType(symbol.type, self))

    # get storage for new symbol
    if self.FN is None:
      storage = MemorySlotStorage(symbol, node.name)
      RE.value = MemorySlotValue(storage)

    else:
      storage = self.get_new_local_storage(len(RE.type.ptr_to_type))
      RE.value = StackSlotValue(storage)

    storage.symbol = symbol
    symbol.storage = storage

    self.DEBUG(self.log_prefix + 'storage: size=%i, slot=%s', len(RE.type.ptr_to_type), storage)

    self.EMIT(Comment('storage: %s => size=%i, slot=%s' % (node.name, len(RE.type.ptr_to_type), RE.value.name)))

    self.DEBUG(self.log_prefix + 'RE=%s', RE)

    if node.init is not None:
      self.DEBUG(self.log_prefix + 'has init, process it')
      self.DOWN()
      self.EMIT(Comment('init of %s' % comment))

      IE = self.visit(node.init)
      self.DEBUG(self.log_prefix + 'init=%s', IE)

      if isinstance(IE.value, RegisterValue):
        self.WARN(self.log_prefix + 'Unhandled init branch')

      else:
        R = self.GET_REG()
        R.dirty = True
        symbol.storage.acquire_register(R)

        self.EMIT(LI(R.name, IE.value.name))
        # self.EMIT(STW(RE.value.name, R.name))

      self.EMIT(Comment('/ init of %s' % comment))
      self.UP()

    self.DEBUG(self.log_prefix + 'declared symbol: %s', symbol)
    self.EMIT(Comment('declared symbol: %s' % symbol))

    # self.EMIT(Comment('/ ' + comment))
    self.UP()
    return RE

  def visit_ExprList(self, node):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    for expr in node.exprs:
      RE = self.visit_expr(expr)

    self.UP()
    return RE

  def visit_FileAST(self, node):
    self.generic_visit(node)

  def visit_For(self, node):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    init_block = self.FN.block(name = self.get_new_label(name = 'for_init'))
    head_block = self.FN.block(name = self.get_new_label(name = 'for_head'))
    body_block = self.FN.block(name = self.get_new_label(name = 'for_body'))
    past_block = self.FN.block(name = self.get_new_label(name = 'for_past'))

    self.break_stack.append(past_block)
    self.continue_stack.append(head_block)

    self.BLOCK.connect(init_block)
    init_block.connect(head_block)
    head_block.connect(body_block)
    head_block.connect(past_block)
    body_block.connect(head_block)
    body_block.connect(past_block)

    self.make_current(init_block)

    IE = self.visit(node.init)
    self.DEBUG(self.log_prefix + '  init=%s', IE)

    self.make_current(head_block)

    self.process_cond(node.cond, iftrue_label = body_block.names[0], iffalse_label = past_block.names[0])

    self.make_current(body_block)
    self.visit(node.stmt)

    self.visit(node.next)
    self.EMIT(J('&' + head_block.names[0]))

    self.make_current(past_block)

    self.break_stack.pop()
    self.continue_stack.pop()

    self.UP()

  def visit_FuncCall(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    self.INFO(self.log_prefix + 'Name: %s', dump_node(node.name))
    self.INFO(self.log_prefix + 'Args: %s', dump_node(node.args))

    if isinstance(node.name, c_ast.ID) and node.name.name == 'asm' and node.args is not None and isinstance(node.args.exprs[0], c_ast.Constant) and node.args.exprs[0].type == 'string':
      for line in node.args.exprs[0].value[1:-1].split('\n'):
        self.EMIT(InlineAsm(line))

      self.UP()
      return None

    FE = self.visit(node.name)
    if FE.value is None:
      raise SymbolUndefined(node.coord, dump_node(node.name))

    FE_symbol = FE.value.storage.symbol

    self.DEBUG(self.log_prefix + 'fn=%s', FE)

    if node.args is not None:
      args = []
      restore_regs = []

      for i, arg in enumerate(node.args.exprs):
        arg_comment = 'arg #%i: %s' % (i, dump_node(arg))

        self.DEBUG(self.log_prefix + arg_comment)
        self.DOWN()
        self.EMIT(Comment(arg_comment))

        R = self.FN.registers.all_regs[i + 1]

        self.EMIT(Comment('free register'))
        if R.storage is None:
          restore_regs.append((R, None))
          self.EMIT(PUSH(R.name))

        else:
          restore_regs.append((R, R.storage))
          R.free()

        self.DEBUG(self.log_prefix + 'place into %s', R)

        A = self.visit(arg, preferred = R.index)

        self.DEBUG(self.log_prefix + 'type=%s', FE_symbol.type.args[i])
        self.DEBUG(self.log_prefix + 'expr=%s', A)

        if not A.is_rvalue():
          A, old_A = A.to_rvalue(self, preferred = R)
          self.DEBUG(self.log_prefix + 'expr=%s', A)

          if isinstance(A.value, RegisterValue) and A.value.register.index != R.index:
            self.EMIT(MOV(R.name, A.value.name))

        elif not isinstance(A.value, RegisterValue):
          self.EMIT(LI(R.name, A.value.name))

        if FE.value.storage.symbol.type.args[i] != A.type:
          A, old_A = self._perform_implicit_conversion(node.coord, A, FE.value.storage.symbol.type.args[i])
          self.DEBUG(self.log_prefix + 'expr=%s', A)

        args.append((R, arg))

        self.UP()

      self.DEBUG(self.log_prefix + 'args: %s', args)

    ret_reg = FE_symbol is not None and len(FE_symbol.type.rtype) != 0 and self.node_parent is not None and not isinstance(self.node_parent, c_ast.Compound)
    self.DEBUG(self.log_prefix + 'return type: %s', FE_symbol.type.rtype)

    if ret_reg:
      RE = Expression(value = RegisterValue(self.GET_REG(preferred = 0)), type = FE_symbol.type.rtype)

    else:
      RE = None

    self.DEBUG(self.log_prefix + 'FN retval: %s', RE)

    if isinstance(FE.value, MemorySlotValue):
      self.EMIT(CALL(FE.value.name))

    else:
      self.WARN(self.log_prefix + 'Unhandled call branch')

    if RE is not None:
      R = self.GET_REG()
      self.EMIT(MOV(R.name, RE.value.name))
      self.PUT_REG(RE.value.register)
      RE.value = RegisterValue(R)

    for R, storage in reversed(restore_regs):
      self.DEBUG(self.log_prefix + 'restore value of %s', R)
      self.EMIT(Comment('restore content of %s' % R))

      if storage is None:
        self.EMIT(POP(R.name))

      else:
        storage.unspill_register(self, R)

    self.INFO(self.log_prefix + 'parent=%s', dump_node(self.node_parent))

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return RE

  def visit_FuncDef(self, node):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    decl = node.decl

    self.INFO(self.log_prefix + 'Decl: %s', dump_node(decl))
    self.INFO(self.log_prefix + 'Type: %s', dump_node(decl.type))
    if decl.type.args is not None:
      self.INFO(self.log_prefix + 'Args: %s', dump_node(decl.type.args))
    self.INFO(self.log_prefix + 'Type type: %s', dump_node(decl.type.type))
    self.INFO(self.log_prefix + 'Return type: %s', dump_node(decl.type.type.type))

    T = CType.create_from_decl(self, decl.type)

    self.reset_scope()
    self.push_scope()

    self.FN = FN = Function(self, decl, T)
    self.functions.append(FN)

    self.GET_REG = FN.registers.get
    self.REGS    = FN.registers

    symbol = self.global_scope.get(decl.name)
    if symbol is None:
      symbol = self.global_scope.add(node.coord, Symbol(self, decl.name, FN.type))

    symbol.storage = MemorySlotStorage(symbol, decl.name)
    symbol.storage.symbol = symbol
    symbol.defined = True

    self.make_current(FN.args_block())

    if decl.type.args is not None:
      for i, arg in enumerate(decl.type.args.params):
        self.visit(arg)

        symbol = self.SCOPE.get(arg.name)
        symbol.defined = True
        self.DEBUG(self.log_prefix + 'arg symbol: %s', symbol)

        R = self.GET_REG(preferred = i + 1)
        R.dirty = True
        symbol.storage.acquire_register(R)

        # self.EMIT(STW(symbol.storage.name(), 'r%i' % (i + 1)))

        self.DEBUG(self.log_prefix + 'arg #%i: %s', i, symbol)
        self.EMIT(Comment('arg #%i: %s' % (i, symbol)))

        del FN.registers.callee_saved_regs[i + 1]

    if len(FN.type.rtype) != 0:
      del FN.registers.callee_saved_regs[0]

    self.make_current(FN.body_block())

    self.visit_Compound(node.body, create_scope = False)

    FN.finish()

    self.UP()

  def visit_ID(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + '%s: preferred=%s, keep=%s', comment, preferred, keep)
    self.DOWN()
    self.EMIT(Comment(comment))

    symbol = self.SCOPE.get(node.name)
    self.DEBUG(self.log_prefix + 'symbol=%s', symbol)

    self.EMIT(Comment('/ ' + comment))

    RE_class = LValueExpression if symbol.const is True else MLValueExpression
    value_class = StackSlotValue if isinstance(symbol.storage, StackSlotStorage) else MemorySlotValue

    RE = RE_class(value = value_class(symbol.storage), type = PointerType(symbol.type, self))

    self.UP()
    return RE

  def visit_If(self, node):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    cond_label    = self.get_new_label(name = 'if_cond')
    iftrue_label  = self.get_new_label(name = 'if_iftrue')
    iffalse_label = self.get_new_label(name = 'if_iffalse')
    past_label    = self.get_new_label(name = 'if_past')

    self.EMIT(Comment(dump_node(node)))
    self.EMIT(Comment('  iftrue=%s, iffalse=%s, past=%s' % (iftrue_label, iffalse_label, past_label)))

    cond_block    = self.FN.block(name = cond_label)
    iftrue_block  = self.FN.block(name = iftrue_label)
    iffalse_block = self.FN.block(name = iffalse_label)

    self.BLOCK.connect(cond_block)
    cond_block.connect(iftrue_block)
    cond_block.connect(iffalse_block)

    self.make_current(cond_block)
    self.process_cond(node.cond, iftrue_label = iftrue_block.names[0], iffalse_label = iffalse_block.names[0])

    self.make_current(iftrue_block)
    self.visit(node.iftrue)

    self.make_current(iffalse_block)
    if node.iffalse is not None:
      self.visit(node.iffalse)

    past_block = self.FN.block(name = past_label)
    iftrue_block.connect(past_block)
    iffalse_block.connect(past_block)

    iftrue_block.emit(J('&' + past_label))
    iffalse_block.emit(J('&' + past_label))

    self.BLOCK.connect(past_block)
    self.EMIT(Comment('connecting %s to %s' % (self.BLOCK, past_block)))
    self.make_current(past_block)

    self.UP()
    return None

  def visit_Return(self, node):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.EMIT(Comment(comment))

    E = self.visit_expr(node.expr)
    self.DEBUG(self.log_prefix + 'expr=%s', E)

    if not E.is_rvalue():
      E, old_E = E.to_rvalue(self, preferred = 0)

    def __free_r0():
      R0 = self.FN.registers.all_regs[0]
      self.EMIT(Comment('free r0'))
      R0.free()
      return R0

    if isinstance(E.value, RegisterValue):
      if E.value.register.index != 0:
        R = __free_r0()
        self.EMIT(MOV(R.name, E.value.name))

      else:
        pass

    elif isinstance(E.value, ConstantValue):
      R = __free_r0()
      self.EMIT(LI(R.name, E.value.name))

    else:
      self.WARN(self.log_prefix + 'Unhandled return branch')

    self.EMIT(J('&' + self.FN.epilog_block().names[0]))
    self.BLOCK.connect(self.FN.epilog_block())

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return None

  def visit_StructRef(self, node, **kwargs):
    comment = dump_node(node)

    self.INFO(self.log_prefix + comment)
    self.DOWN()
    self.INFO(self.log_prefix + 'name=%s, field=%s', dump_node(node.name), dump_node(node.field))

    self.EMIT(Comment(comment))

    NE = self.visit_expr(node.name)
    self.DEBUG(self.log_prefix + 'name=%s', NE)

    RE_class = NE.__class__
    self.DEBUG(self.log_prefix + 'RE class=%s', RE_class.__name__)

    if node.type == '->':
      if not isinstance(NE.type.ptr_to_type, PointerType):
        raise NotAPointerError(node.coord, NE.type)

      RE_class = MLValueExpression

      old_NE = NE
      NE = LValueExpression(value = RegisterMemorySlotValue(self.GET_REG()), type = NE.type.ptr_to_type)

      self.EMIT(LW(NE.value.name, old_NE.value.name))

    if isinstance(NE.type.ptr_to_type, PointerType):
      raise IsAPointerError(node.coord, NE.type)

    field_type = NE.type.ptr_to_type.field_type(node.field.name)
    field_offset = NE.type.ptr_to_type.field_offset(node.field.name)

    self.DEBUG(self.log_prefix + 'field_type=%s, field_offset=%s', field_type, field_offset)

    RE = None

    if isinstance(NE.value, StackSlotValue):
      RE = RE_class(value = StackSlotValue(StackSlotStorage(None, NE.value.storage.offset + field_offset)), type = PointerType(field_type, self))

    elif isinstance(NE.value, RegisterMemorySlotValue):
      RE = RE_class(value = NE.value, type = PointerType(field_type, self))
      self.EMIT(ADD(RE.value.name, field_offset))

    elif isinstance(NE.value, MemorySlotValue):
      RE = RE_class(value = RegisterValue(self.GET_REG()), type = PointerType(field_type, self))
      NE.value.storage.addrof(RE.value.register, self.EMIT)
      self.EMIT(ADD(RE.value.name, field_offset))

    else:
      self.WARN(self.log_prefix + 'Unhandled struct ref for name')

    self.EMIT(Comment('/ ' + comment))
    self.UP()
    return RE

  def visit_TypeDecl(self, node, **kwargs):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    t = CType.create_from_decl(self, node)

    self.types[node.declname] = t

    self.UP()
    return RValueExpression(type = t)

  def visit_Typedef(self, node):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    ts = self.generic_visit(node)
    T = ts[0]
    self.types[node.name] = T.type
    self.DEBUG(self.log_prefix + 'typedef new type: %s', T)

    self.UP()
    return RValueExpression(type = T)

  def visit_Typename(self, node, **kwargs):
    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()

    T = CType.get_from_decl(self, node.type)

    self.UP()
    return RValueExpression(type = T)

  def visit_UnaryOp(self, node, preferred = None, keep = None):
    comment = dump_node(node)

    self.INFO(self.log_prefix + '%s, preferred=%s, keep=%s', comment, preferred, keep)
    self.DOWN()
    self.EMIT(Comment(comment))

    keep = keep or []

    E = self.visit_expr(node.expr)
    self.DEBUG(self.log_prefix + 'expr=%s', E)

    if node.op == 'p++':
      assert E.is_mlvalue() is True

      E, old_E = E.to_rvalue(self)

      self.DEBUG(self.log_prefix + 'expr=%s', E)

      RE = RValueExpression(value = self.GET_REG(), type = E.type)

      self.EMIT(MOV(RE.value.name, E.value.name))
      self.EMIT(INC(E.value.name))

      if old_E.value.is_register_backed():
        old_E.value.backing_register().dirty = True

      else:
        if len(E.type) == 1:
          self.EMIT(STB(old_E.value.name, E.value.name))

        elif len(E.type) == 2:
          self.EMIT(STB(old_E.value.name, E.value.name))

        else:
          self.WARN(self.log_prefix + 'Unhandled save branch')

      self.DEBUG(self.log_prefix + 'postfix inc: expr=%s, rexpr=%s', E, RE)

      self.EMIT(Comment('/ ' + comment))
      self.UP()
      return RE

    if node.op == '*':
      assert isinstance(E.type, PointerType) is True

      RE = E.__class__(value = RegisterValue(self.GET_REG(preferred = preferred, keep = keep + [E.value])), type = E.type.ptr_to_type)

      if len(RE.type) == 1:
        self.EMIT(LB(RE.value.name, E.value.name))

      elif len(RE.type) == 2:
        self.EMIT(LW(RE.value.name, E.value.name))

      else:
        self.WARN(self.log_prefix + 'Unhandled deref branch')

      self.EMIT(Comment('/ ' + comment))
      self.UP()
      return RE

    if node.op == '&':
      assert E.is_lvalue() is True

      if E.value.is_register_backed():
        E.value.storage.spill_register(self)

      if isinstance(E.value, StackSlotValue):
        RE = RValueExpression(value = RegisterValue(self.GET_REG()), type = E.type)
        E.value.storage.addrof(RE.value, self.EMIT)

      elif isinstance(E.value, RegisterMemorySlotValue):
        RE = RValueExpression(value = E.value, type = E.type)

      else:
        self.WARN(self.log_prefix + 'Unhandled addrof branch')

      self.EMIT(Comment('/ ' + comment))
      self.UP()
      return RE

    if node.op == '~':
      if E.is_lvalue():
        RE, old_E = E.to_rvalue(self)

      else:
        RE = RValueExpression(value = RegisterValue(self.GET_REG()), type = E.type)

      if isinstance(E.value, ConstantValue):
        self.EMIT(LI(RE.value.name, E.value.name))

      self.EMIT(NOT(RE.value.name))

      self.EMIT(Comment('/ ' + comment))
      self.UP()
      return RE

    if node.op == 'sizeof':
      RE = RValueExpression(value = RegisterValue(self.GET_REG(preferred = preferred, keep = keep)), type = UnsignedIntType(self))
      self.EMIT(LI(RE.value.name, len(E.type)))

      self.UP()
      return RE

    self.WARN('Unhandled unary op: op=%s', node.op)

    self.UP()
    return None, None, None

  def visit_While(self, node):
    comment = dump_node(node)

    self.INFO(self.log_prefix + dump_node(node))
    self.DOWN()
    self.EMIT(Comment(comment))

    head_block = self.FN.block(name = self.get_new_label(name = 'while_head'))
    body_block = self.FN.block(name = self.get_new_label(name = 'while_body'))
    past_block = self.FN.block(name = self.get_new_label(name = 'while_past'))

    self.break_stack.append(past_block.names[0])
    self.continue_stack.append(head_block.names[0])

    self.BLOCK.connect(head_block)
    head_block.connect(body_block)
    head_block.connect(past_block)
    body_block.connect(head_block)
    body_block.connect(past_block)

    self.DEBUG(self.log_prefix + 'head_block: %s', head_block)

    self.make_current(head_block)

    self.process_cond(node.cond, iffalse_label = past_block.names[0])

    self.make_current(body_block)
    self.visit(node.stmt)
    self.EMIT(J('&' + head_block.names[0]))

    self.make_current(past_block)

    self.break_stack.pop()
    self.continue_stack.pop()

    self.EMIT(Comment('/ ' + comment))
    self.UP()

from . import AST_PASSES
AST_PASSES['ast-codegen'] = CodegenVisitor
