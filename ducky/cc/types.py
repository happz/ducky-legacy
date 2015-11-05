import collections

from pycparser import c_ast

import ducky.cpu
import ducky.util

from . import dump_node, UndefinedStructMemberError

class CType(object):
  types = {}

  def __init__(self, visitor, decl = None):
    self.visitor = visitor
    self.decl = decl

  def __repr__(self):
    raise NotImplementedError('Type %s does not provide its representation' % self.__class__.__name__)

  def __len__(self):
    raise NotImplementedError('Type %s does not provide its size' % self.__class__.__name__)

  def __cmp__(self, other):
    return 0 if repr(self) == repr(other) else -1

  def __eq__(self, other):
    return repr(self) == repr(other)

  def __neq__(self, other):
    return repr(self) != repr(other)

  @staticmethod
  def get_from_desc(visitor, desc):
    visitor.DEBUG(visitor.log_prefix + 'Type.get_from_desc: desc=%s', desc)
    visitor.DOWN()

    T = visitor.types.get(desc)

    if T is None:
      raise RuntimeError('Unknown type: %s' % desc)

    visitor.UP()
    return T

  @staticmethod
  def get_from_decl(visitor, decl):
    visitor.DEBUG(visitor.log_prefix + 'Type.get_from_decl: decl=%s', dump_node(decl))
    visitor.DOWN()

    T = None

    if isinstance(decl, c_ast.PtrDecl):
      T = PointerType(CType.get_from_decl(visitor, decl.type), visitor, decl)

    elif isinstance(decl.type, c_ast.IdentifierType):
      name = ' '.join(decl.type.names)

    elif isinstance(decl.type, c_ast.Struct):
      name = 'struct ' + decl.type.name

    elif isinstance(decl.type, c_ast.PtrDecl):
      T = PointerType(CType.get_from_decl(visitor, decl.type), visitor, decl)

    elif isinstance(decl, c_ast.ArrayDecl):
      T = ArrayType(CType.get_from_decl(visitor, decl.type), visitor, decl)

    else:
      visitor.WARN(visitor.log_prefix + 'Unhandled get_from_decl branch: %s', decl.type.__class__.__name__)
      visitor.UP()
      return None

    if T is None:
      visitor.DEBUG(visitor.log_prefix + 'searching for "%s"', name)
      visitor.DEBUG(visitor.log_prefix + 'known types: %s', visitor.types)

      T = visitor.types.get(name)

    if T is None:
      raise RuntimeError('Unknown type: %s' % name)

    visitor.UP()
    return T

  @staticmethod
  def create_from_decl(visitor, decl):
    visitor.DEBUG(visitor.log_prefix + 'Type.create_from_decl: decl=%s', dump_node(decl))
    visitor.DOWN()

    T = None

    if isinstance(decl, c_ast.PtrDecl):
      T = PointerType(CType.get_from_decl(visitor, decl.type), visitor, decl)

    elif isinstance(decl, c_ast.FuncDecl):
      T = FunctionType(visitor, decl)

    elif isinstance(decl, c_ast.ArrayDecl):
      T = ArrayType(CType.get_from_decl(visitor, decl.type), visitor, decl)

    elif isinstance(decl.type, c_ast.Struct):
      if decl.type.decls is None and decl.type.name is not None:
        T = CType.get_from_decl(visitor, decl)

      else:
        name = visitor.get_new_label() if decl.type.name is None else decl.type.name
        visitor.DEBUG(visitor.log_prefix + 'Type.create_from_decl: struct: %s', dump_node(decl.type))
        T = StructType(name, visitor, decl.type)

    elif isinstance(decl.type, c_ast.IdentifierType):
      T = CType.get_from_decl(visitor, decl)

    else:
      visitor.WARN(visitor.log_prefix + 'Unhandled branch')

    visitor.DEBUG(visitor.log_prefix + 'Type.create_from_decl: %s => %s', dump_node(decl), T)

    visitor.UP()
    return T

class VoidType(CType):
  def __repr__(self):
    return 'void'

  def __len__(self):
    return 0

class IntType(CType):
  def __repr__(self):
    return 'int'

  def __len__(self):
    return 2

class UnsignedIntType(IntType):
  def __repr__(self):
    return 'unsigned int'

class CharType(CType):
  def __repr__(self):
    return 'char'

  def __len__(self):
    return 1

class UnsignedCharType(CharType):
  def __repr__(self):
    return 'unsigned char'

class PointerType(CType):
  def __init__(self, ptr_to_type, *args, **kwargs):
    super(PointerType, self).__init__(*args, **kwargs)

    self.ptr_to_type = ptr_to_type

  def __repr__(self):
    return repr(self.ptr_to_type) + '*'

  def __len__(self):
    return 2

class StructType(CType):
  def __init__(self, name, *args, **kwargs):
    super(StructType, self).__init__(*args, **kwargs)

    self.name = name
    self.fields = collections.OrderedDict()

    self._size = 0

    class Field(object):
      def __init__(self, name, type, offset):
        self.name = name
        self.type = type
        self.offset = offset

    field_offset = 0
    for field in self.decl.decls:
      if isinstance(field.type, c_ast.PtrDecl):
        field_type = PointerType(CType.get_from_decl(self.visitor, field.type.type), self.visitor, field.type.type)

      else:
        field_type = CType.get_from_decl(self.visitor, field.type)

      self.fields[field.name] = field = Field(field.name, field_type, field_offset)

      field_offset = ducky.util.align(2, field_offset + len(field.type))

    self._size = ducky.util.align(2, field_offset)

  def __repr__(self):
    return 'struct %s' % self.name

  def __len__(self):
    return self._size

  def field_offset(self, name):
    if name not in self.fields:
      raise UndefinedStructMemberError(None, self, name)

    return self.fields[name].offset

  def field_type(self, name):
    return self.fields[name].type

class FunctionType(CType):
  def __init__(self, *args, **kwargs):
    super(FunctionType, self).__init__(*args, **kwargs)

    self.rtype = None
    self.args = []

    self.visitor.DEBUG(self.visitor.log_prefix + 'create rtype')
    self.rtype = CType.get_from_decl(self.visitor, self.decl.type)

    if self.decl.args is not None:
      for arg in self.decl.args.params:
        self.args.append(CType.get_from_decl(self.visitor, arg.type))

  def __repr__(self):
    return '%s(%s)' % (repr(self.rtype), ', '.join([repr(param) for param in self.args]))

class ArrayType(CType):
  def __init__(self, item_type, size = None, *args, **kwargs):
    super(ArrayType, self).__init__(*args, **kwargs)

    self.item_type = item_type
    self.size = None

  def __repr__(self):
    return repr(self.item_type) + '[]'

  def __len__(self):
    if self.size is not None:
      return self.size
    return 2
