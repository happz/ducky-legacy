import collections
import enum
import os

from six import iteritems, iterkeys, itervalues
from six.moves import cStringIO as StringIO

import ducky.cpu
import ducky.util

def dump_node(node):
  line = None

  if node.coord is not None and node.coord.line != 0:
    with open(node.coord.file, 'r') as f:
      line = f.readlines()[node.coord.line - 1].strip()

  ignore = ['attr_names', 'children', 'show']
  return '%s(%s)%s' % (node.__class__.__name__, ', '.join(['%s=%s' % (name, getattr(node, name)) for name in dir(node) if not name.startswith('__') and name not in ignore]), ' [' + line + ']' if line is not None else '')

def show_node(node):
  buff = StringIO()
  node.show(buf = buff, attrnames = True)
  return buff.getvalue().strip()

class CompilerError(Exception):
  def __init__(self, location, msg):
    super(CompilerError, self).__init__('%s:%s: %s' % (os.path.abspath(location.file), location.line, msg))

class SymbolAlreadyDefinedError(CompilerError):
  def __init__(self, loc, symbol):
    super(SymbolAlreadyDefinedError, self).__init__(loc, 'Symbol already defined: name=%s' % symbol)

class SymbolConflictError(CompilerError):
  pass

class SymbolUndefined(CompilerError):
  def __init__(self, loc, symbol):
    super(SymbolUndefined, self).__init__(loc, 'Undefined symbol: name=%s' % symbol)

class IncompatibleTypesError(CompilerError):
  def __init__(self, loc, t1, t2):
    super(IncompatibleTypesError, self).__init__(loc, 'Incompatible types: "%s" cannot be matched with "%s"' % (t1, t2))

class UnableToImplicitCastError(CompilerError):
  def __init__(self, loc, t1, t2):
    super(UnableToImplicitCastError, self).__init__(loc, 'Unable to perform implicit cast: "%s" => "%s"' % (t1, t2))

class NotAPointerError(CompilerError):
  def __init__(self, loc, t):
    super(NotAPointerError, self).__init__(loc, 'Type is not a pointer: "%s"' % t)

class IsAPointerError(CompilerError):
  def __init__(self, loc, t):
    super(IsAPointerError, self).__init__(loc, 'Type is a pointer: "%s"' % t)

class UndefinedStructMemberError(CompilerError):
  def __init__(self, loc, s, m):
    super(UndefinedStructMemberError, self).__init__(loc, 'Unknown structure member: "%s.%s"' % (s, m))

class Symbol(object):
  def __init__(self, visitor, name, decl_type, extern = False, defined = False, const = False):
    self.visitor = visitor
    self.name = name
    self.type = decl_type

    self.extern = extern
    self.defined = defined
    self.const = const

    self.storage = None

  def __repr__(self):
    return '<Symbol: name=%s, type=%s, storage=%s, extern=%s, defined=%s, const=%s>' % (self.name, self.type, repr(self.storage) if self.storage is not None else '<none>', self.extern, self.defined, self.const)


class SymbolStorage(object):
  def __init__(self, symbol, register = None):
    self.symbol = symbol

    self.register = register

  def __repr__(self):
    return '<%s: symbol=%s, register=%s>' % (self.__class__.__name__, self.symbol.name if self.symbol is not None else '<none>', self.register.name if self.register is not None else '<none>')

  def addrof(self, reg, emit):
    raise NotImplementedError('Storage %s does not provide addrof operator' % self.__class__.__name__)

  def name(self):
    raise NotImplementedError('Storage %s does not provide name operator' % self.__class__.__name__)

  def has_register(self):
    return self.register is not None

  def acquire_register(self, register):
    assert self.register is None
    assert register.storage is None

    self.register = register
    register.storage = self

  def release_register(self):
    assert self.register is not None

    self.register.storage = None
    self.register = None

  def spill_register(self, visitor):
    visitor.DEBUG(visitor.log_prefix + 'spill_register: reg=%s', self.register)

    if not self.has_register():
      return

    if self.register.dirty is not True:
      return

    if len(self.symbol.type) == 1:
      visitor.EMIT(STB(self.name(), self.register.name))

    elif len(self.symbol.type) == 2:
      visitor.EMIT(STW(self.name(), self.register.name))

    else:
      visitor.WARN(visitor.log_prefix + 'Unhandled spill size branch')

    self.register.dirty = False

  def unspill_register(self, visitor, register):
    if self.register is not None:
      visitor.WARN(visitor.log_prefix + 'Storage already has a register!')
      return

    self.acquire_register(register)
    self.register.dirty = False

    if len(self.symbol.type) == 1:
      visitor.EMIT(LB(self.register.name, self.name()))

    elif len(self.symbol.type) == 2:
      visitor.EMIT(LW(self.register.name, self.name()))

    else:
      visitor.WARN(visitor.log_prefix + 'Unhandled unspill size branch')

class StackSlotStorage(SymbolStorage):
  def __init__(self, symbol, offset):
    super(StackSlotStorage, self).__init__(symbol)

    self.offset = offset

  def addrof(self, register, emit):
    emit(MOV(register.name, 'fp'))
    emit(ADD(register.name, self.offset))

  def name(self):
    return 'fp[%i]' % self.offset

class MemorySlotStorage(SymbolStorage):
  def __init__(self, symbol, label):
    super(MemorySlotStorage, self).__init__(symbol)

    self.label = '&%s' % label

  def addrof(self, register, emit):
    emit(LI(register.name, self.label))

  def name(self):
    return self.label

class Scope(object):
  scope_id = 0

  def __init__(self, visitor, parent = None):
    self.visitor = visitor

    self.id = Scope.scope_id
    Scope.scope_id += 1

    self.parent = parent

    self.symbols = {}

  def __repr__(self):
    return '<Scope: id=%i>' % self.id

  def add(self, loc, symbol):
    self.visitor.DEBUG(self.visitor.log_prefix + 'scope: add symbol: scope=%s, symbol=%s', self, symbol)

    old_symbol = self.symbols.get(symbol.name)

    if old_symbol is not None:
      if old_symbol.defined:
        if symbol.defined:
          raise SymbolAlreadyDefinedError(loc, symbol.name)

        else:
          return old_symbol

      else:
        self.symbols[symbol.name] = symbol
        return symbol

    self.symbols[symbol.name] = symbol
    return symbol

  def get(self, name):
    self.visitor.DEBUG(self.visitor.log_prefix + 'scope: get symbol: scope=%s, symbol=%s', self, name)

    if name in self.symbols:
      return self.symbols[name]

    if self.parent is not None:
      return self.parent.get(name)

    return None


class Register(object):
  def __init__(self, rset, index):
    self.set = rset
    self.index = index

    self.name = 'r%i' % index

    self.visitor = self.set.visitor

    self.storage = None
    self.dirty = False

  def __repr__(self):
    return '<%s: storage=%s, dirty=%s>' % (self.name, self.storage.name() if self.storage is not None else '<none>', self.dirty)

  def put(self):
    self.visitor.DEBUG(self.visitor.log_prefix + 'Register.put: reg=%s', self)

    if self.storage is None:
      self.set.free_regs[self.index] = self

      self.visitor.EMIT(Comment('reg %s released' % self.name))

    else:
      self.visitor.DEBUG(self.visitor.log_prefix + 'Register.put: register acquired by storage, not free')

    self.visitor.DEBUG(self.visitor.log_prefix + 'free regs: %s', list(iterkeys(self.set.free_regs)))

  def free(self):
    self.visitor.DEBUG(self.visitor.log_prefix + 'Register.free: reg=%s', self)
    self.visitor.DEBUG(self.visitor.log_prefix + '  free regs: %s', list(iterkeys(self.set.free_regs)))

    if self.storage is not None:
      self.storage.spill_register(self.visitor)
      self.storage.release_register()

    self.set.free_regs[self.index] = self

    self.visitor.EMIT(Comment('reg %s forcefully freed' % self.name))
    return self

class RegisterSet(object):
  def __init__(self, fn):
    self.fn = fn
    self.visitor = fn.visitor

    self.all_regs = collections.OrderedDict([(r.value, Register(self, r.value)) for r in ducky.cpu.registers.GENERAL_REGISTERS])
    self.free_regs = self.all_regs.copy()
    self.used_regs = collections.OrderedDict()

    self.callee_saved_regs = self.all_regs.copy()

    self.context_stack = []

    self.DEBUG = self.visitor.DEBUG

  def save_callee_saves(self, block):
    self.DEBUG(self.visitor.log_prefix + 'RegisterSet.save_callee_saves: used_regs=%s, callee_saves=%s', sorted([r.index for r in iterkeys(self.used_regs)]), sorted(list(iterkeys(self.callee_saved_regs))))

    for reg in sorted(list(iterkeys(self.used_regs)), key = lambda x: x.index):
      if reg.index not in self.callee_saved_regs:
        continue

      self.DEBUG(self.visitor.log_prefix + '  save %s', reg.name)
      block.emit(PUSH(reg.name))

  def restore_callee_saves(self, block):
    self.DEBUG(self.visitor.log_prefix + 'RegisterSet.restore_callee_saves: used_regs=%s, callee_saves=%s', sorted([r.index for r in iterkeys(self.used_regs)]), sorted(list(iterkeys(self.callee_saved_regs))))

    for reg in reversed(sorted(list(iterkeys(self.used_regs)), key = lambda x: x.index)):
      if reg.index not in self.callee_saved_regs:
        continue

      block.emit(POP(reg.name))

  def get(self, preferred = None, keep = None):
    self.DEBUG(self.visitor.log_prefix + 'RegisterSet.get: preferred=%s, keep=%s', preferred, keep)
    self.DEBUG(self.visitor.log_prefix + '  free regs: %s', list(iterkeys(self.free_regs)))

    if self.free_regs:
      selected = None

      if preferred is not None:
        for i, reg in iteritems(self.free_regs):
          self.DEBUG(self.visitor.log_prefix + '    consider %i: %s', i, reg)
          if i != preferred and reg != preferred:
            continue

          selected = reg
          break

      else:
        selected = self.free_regs[sorted(list(iterkeys(self.free_regs)))[-1]]

      self.DEBUG(self.visitor.log_prefix + '  selected reg: %s', selected)

      if selected is not None:
        del self.free_regs[selected.index]
        self.used_regs[selected] = True
        self.visitor.EMIT(Comment('reg %s acquired' % selected.name))
        return selected

    return self.__spoil_any_reg(keep = keep)

  def __enter__(self, *args, **kwargs):
    r = self.get(*args, **kwargs)
    self.context_stack.append(r)
    return r

  def __exit__(self, *args, **kwargs):
    R = self.context_stack.pop()
    R.free()

from ducky.cpu.instructions import DuckyOpcodes, DuckyInstructionSet

class Instruction(object):
  def __init__(self, opcode, *operands):
    self.opcode = opcode
    self.operands = operands

    for inst in DuckyInstructionSet.instructions:
      if inst.opcode != opcode:
        continue

      self.mnemonic = inst.mnemonic
      break

    self.labels = []

  def __repr__(self):
    return self.materialize()

  def materialize(self):
    if self.operands:
      return '%s %s' % (self.mnemonic, ', '.join([str(o) for o in self.operands]))
    else:
      return self.mnemonic

class Directive(Instruction):
  def __init__(self, directive):
    super(Directive, self).__init__(None)

    self.directive = directive

  def materialize(self):
    return self.directive

class Comment(object):
  def __init__(self, comment):
    self.comment = comment

  def materialize(self):
    return '; %s' % self.comment

class InlineAsm(Instruction):
  def __init__(self, code):
    super(InlineAsm, self).__init__(None)

    self.code = code

  def materialize(self):
    return self.code

class ADD(Instruction):
  def __init__(self, *operands):
    super(ADD, self).__init__(DuckyOpcodes.ADD, *operands)

class AND(Instruction):
  def __init__(self, *operands):
    super(AND, self).__init__(DuckyOpcodes.AND, *operands)

class BGE(Instruction):
  def __init__(self, label):
    super(BGE, self).__init__(DuckyOpcodes.BGE, label)

class BLE(Instruction):
  def __init__(self, label):
    super(BLE, self).__init__(DuckyOpcodes.BLE, label)

class BNE(Instruction):
  def __init__(self, label):
    super(BNE, self).__init__(DuckyOpcodes.BNE, label)

class BE(Instruction):
  def __init__(self, label):
    super(BE, self).__init__(DuckyOpcodes.BE, label)

class BG(Instruction):
  def __init__(self, label):
    super(BG, self).__init__(DuckyOpcodes.BG, label)

class BL(Instruction):
  def __init__(self, label):
    super(BL, self).__init__(DuckyOpcodes.BL, label)

class CMP(Instruction):
  def __init__(self, left, right):
    super(CMP, self).__init__(DuckyOpcodes.CMP, left, right)

class CALL(Instruction):
  def __init__(self, label):
    super(CALL, self).__init__(DuckyOpcodes.CALL, label)

class INT(Instruction):
  def __init__(self, isr):
    super(INT, self).__init__(DuckyOpcodes.INT, isr)

class INC(Instruction):
  def __init__(self, reg):
    super(INC, self).__init__(DuckyOpcodes.INC, reg)

class J(Instruction):
  def __init__(self, label):
    super(J, self).__init__(DuckyOpcodes.J, label)

class LB(Instruction):
  def __init__(self, reg, addr):
    super(LB, self).__init__(DuckyOpcodes.LB, reg, addr)

class LW(Instruction):
  def __init__(self, reg, addr):
    super(LW, self).__init__(DuckyOpcodes.LW, reg, addr)

class LI(Instruction):
  def __init__(self, reg, value):
    super(LI, self).__init__(DuckyOpcodes.LI, reg, value)

class MOV(Instruction):
  def __init__(self, *operands):
    super(MOV, self).__init__(DuckyOpcodes.MOV, *operands)

class MUL(Instruction):
  def __init__(self, *operands):
    super(MUL, self).__init__(DuckyOpcodes.MUL, *operands)

class OR(Instruction):
  def __init__(self, *operands):
    super(MUL, self).__init__(DuckyOpcodes.MUL, *operands)

class NOT(Instruction):
  def __init__(self, *operands):
    super(NOT, self).__init__(DuckyOpcodes.NOT, *operands)

class POP(Instruction):
  def __init__(self, reg):
    super(POP, self).__init__(DuckyOpcodes.POP, reg)

class PUSH(Instruction):
  def __init__(self, reg):
    super(PUSH, self).__init__(DuckyOpcodes.PUSH, reg)

class RET(Instruction):
  def __init__(self):
    super(RET, self).__init__(DuckyOpcodes.RET)

class SHL(Instruction):
  def __init__(self, reg, ri):
    super(SHL, self).__init__(DuckyOpcodes.SHIFTL, reg, ri)

class SHR(Instruction):
  def __init__(self, reg, ri):
    super(SHR, self).__init__(DuckyOpcodes.SHIFTR, reg, ri)

class STB(Instruction):
  def __init__(self, addr, reg):
    super(STB, self).__init__(DuckyOpcodes.STB, addr, reg)

class STW(Instruction):
  def __init__(self, addr, reg):
    super(STW, self).__init__(DuckyOpcodes.STW, addr, reg)

class SUB(Instruction):
  def __init__(self, *operands):
    super(SUB, self).__init__(DuckyOpcodes.SUB, *operands)


class NamedValue(object):
  def __init__(self, name):
    super(NamedValue, self).__init__()

    self.name = name

  def __repr__(self):
    return '<%s: %s, rb=%s>' % (self.__class__.__name__, self.name, self.is_register_backed())

  def can_register_backed(self):
    return isinstance(self, StackSlotValue) or isinstance(self, MemorySlotValue)

  def is_register_backed(self):
    return (isinstance(self, StackSlotValue) or isinstance(self, MemorySlotValue)) and self.storage.has_register()

  def backing_register(self):
    assert isinstance(self, StackSlotValue) or isinstance(self, MemorySlotValue)

    return self.storage.register

class RegisterValue(NamedValue):
  def __init__(self, register):
    assert isinstance(register, Register)

    super(RegisterValue, self).__init__(register.name)

    self.register = register

class StackSlotValue(NamedValue):
  def __init__(self, storage):
    super(StackSlotValue, self).__init__('fp[%i]' % storage.offset)

    self.storage = storage

class MemorySlotValue(NamedValue):
  def __init__(self, storage):
    super(MemorySlotValue, self).__init__(storage.label)

    self.storage = storage

class RegisterMemorySlotValue(NamedValue):
  def __init__(self, register):
    super(RegisterMemorySlotValue, self).__init__(register.name)

    self.register = register

class ConstantValue(NamedValue):
  def __init__(self, value):
    super(ConstantValue, self).__init__(value)

    self.value = value

class ExpressionClass(enum.Enum):
  LVALUE  = 0
  MLVALUE = 1
  RVALUE  = 2

class Expression(object):
  def __init__(self, value = None, type = None, klass = ExpressionClass.RVALUE):
    if self.__class__ is Expression:
      raise RuntimeError('It is not possible to create Expression object - use one of its children, [M][LR]ValueExpression instead')

    self.value = value
    self.type = type
    self.klass = klass

  def __repr__(self):
    return '<%s: value=%s, type=%s>' % (self.__class__.__name__, self.value, self.type)

  def is_lvalue(self):
    return self.klass in (ExpressionClass.LVALUE, ExpressionClass.MLVALUE)

  def is_mlvalue(self):
    return self.klass == ExpressionClass.MLVALUE

  def is_rvalue(self):
    return self.klass == ExpressionClass.RVALUE

  def to_rvalue(self, visitor, preferred = None, keep = None):
    assert self.is_lvalue() is True

    visitor.DEBUG(visitor.log_prefix + 'to_rvalue: E=%s', self)
    visitor.DOWN()

    visitor.EMIT(Comment('<lvalue->rvalue conversion: %s' % self))

    RE = RValueExpression(type = self.type.ptr_to_type)

    from .types import ArrayType
    if isinstance(self.type, ArrayType):
      self.WARN(self.log_prefix + 'Implicit array->ptr conversion')

    else:
      if isinstance(self.value, StackSlotValue) or isinstance(self.value, MemorySlotValue):
        storage = self.value.storage

        if storage.has_register():
          visitor.DEBUG(visitor.log_prefix + 'to_rvalue: E is symbol storage already having a register')
          RE.value = RegisterValue(storage.register)

        else:
          visitor.DEBUG(visitor.log_prefix + 'to_rvalue: E is symbol storage without a register')

          RE.value = RegisterValue(visitor.GET_REG(preferred = preferred, keep = keep))
          storage.acquire_register(RE.value.register)

          if len(self.type.ptr_to_type) == 1:
            visitor.EMIT(LB(RE.value.name, self.value.name))

          elif len(self.type.ptr_to_type) == 2:
            visitor.EMIT(LW(RE.value.name, self.value.name))

          else:
            visitor.WARN(visitor.log_prefix + 'Unhandled lvalue->rvalue size branch')

      else:
        visitor.DEBUG(visitor.log_prefix + 'to_rvalue: E is generic value')

        RE = RValueExpression(value = RegisterValue(visitor.GET_REG(preferred = preferred, keep = keep)), type = self.type.ptr_to_type)

        visitor.DEBUG(visitor.log_prefix + 'RE=%s', RE)

        if len(self.type.ptr_to_type) == 1:
          visitor.EMIT(LB(RE.value.name, self.value.name))

        elif len(self.type.ptr_to_type) == 2:
          visitor.EMIT(LW(RE.value.name, self.value.name))

        else:
          visitor.WARN(visitor.log_prefix + 'Unhandled lvalue->rvalue size branch')

    visitor.DEBUG(visitor.log_prefix + 'RE=%s', RE)

    visitor.EMIT(Comment('</ lvalue->rvalue conversion: %s>' % RE))
    visitor.UP()
    return RE, self

class LValueExpression(Expression):
  def __init__(self, *args, **kwargs):
    super(LValueExpression, self).__init__(klass = ExpressionClass.LVALUE, *args, **kwargs)

class MLValueExpression(Expression):
  def __init__(self, *args, **kwargs):
    super(MLValueExpression, self).__init__(klass = ExpressionClass.MLVALUE, *args, **kwargs)

class RValueExpression(Expression):
  def __init__(self, *args, **kwargs):
    super(RValueExpression, self).__init__(klass = ExpressionClass.RVALUE, *args, **kwargs)

class Block(object):
  id = 0

  def __init__(self, name = None, comment = None):
    Block.id += 1
    self.id = Block.id

    self.names = [name] if name is not None else []

    self.comment = comment

    self.code = []

    self.incoming = {}
    self.outgoing = {}

  def __repr__(self):
    return 'Block(id=%i, names=%s, in=%s, out=%s%s)' % (self.id, ','.join(self.names), ','.join([str(block.id) for block in itervalues(self.incoming)]), ','.join([str(block.id) for block in itervalues(self.outgoing)]), (' (%s)' % self.comment) if self.comment is not None else '')

  def instructions(self):
    return [i for i in self.code if isinstance(i, Instruction)]

  def add_name(self, name):
    self.names.append(name)

  def emit(self, inst):
    self.code.append(inst)

  def add_outgoing(self, block):
    self.outgoing[block.id] = block

  def add_incoming(self, block):
    self.incoming[block.id] = block

  def connect(self, next):
    self.outgoing[next.id] = next
    next.incoming[self.id] = self

  def materialize(self, code):
    code.append('')
    code.append('  ; block: id=%s, names=%s, in=%s, out=%s%s' % (self.id, ', '.join(self.names), ', '.join([str(block.id) for block in itervalues(self.incoming)]), ', '.join([str(block.id) for block in itervalues(self.outgoing)]), (' (%s)' % self.comment) if self.comment is not None else ''))

    for name in self.names:
      code.append('%s:' % name)

    for inst in self.code:
      if hasattr(inst, 'materialize'):
        code.append('  ' + inst.materialize())

      else:
        code.append(inst)

class Function(object):
  def __init__(self, visitor, decl, ftype, args_types = None):
    self.visitor = visitor
    self.decl = decl
    self.registers = RegisterSet(self)

    self.name = decl.name

    self.type = ftype

    self.fp_offset = 0

    self.blocks = []

    self._header_block = self.block(comment = '%s header' % decl.name)
    self._prolog_block = self.block(name = decl.name, comment = '%s prolog' % decl.name)
    self._args_block   = self.block(comment = '%s args' % decl.name)
    self._body_block   = self.block(comment = '%s body' % decl.name)
    self._epilog_block = Block(name = visitor.get_new_label(name = self.name + '_return'), comment = '%s epilog' % decl.name)

    self._header_block.connect(self._prolog_block)
    self._prolog_block.connect(self._args_block)
    self._args_block.connect(self._body_block)

  def block(self, *args, **kwargs):
    block = Block(*args, **kwargs)
    self.blocks.append(block)
    return block

  def header_block(self):
    return self._header_block

  def prolog_block(self):
    return self._prolog_block

  def args_block(self):
    return self._args_block

  def body_block(self):
    return self._body_block

  def epilog_block(self):
    return self._epilog_block

  def finish(self):
    self.header_block().emit(Directive('.text'))

    if 'static' not in self.decl.storage:
      self.header_block().emit(Directive('.global {name}'.format(name = self.decl.name)))

    self.blocks[-1].connect(self.epilog_block())
    self.blocks.append(self.epilog_block())

    self.prolog_block().emit(SUB('sp', abs(self.fp_offset)))
    self.registers.save_callee_saves(self.prolog_block())

    self.registers.restore_callee_saves(self.epilog_block())
    self.epilog_block().emit(ADD('sp', abs(self.fp_offset)))
    self.epilog_block().emit(RET())

  def materialize(self):
    code = []

    for block in self.blocks:
      block.materialize(code)

    return code
