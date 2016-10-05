class SourceLocation(object):
  __slots__ = ('filename', 'lineno', 'column', 'length')

  def __init__(self, filename = None, lineno = None, column = None, length = None):
    self.filename = filename
    self.lineno = lineno
    self.column = column
    self.length = length

  def copy(self):
    return SourceLocation(filename = self.filename, lineno = self.lineno, column = self.column, length = self.length)

  def __str__(self):
    t = [str(self.filename), str(self.lineno)]

    if self.column is not None:
      t.append(str(self.column))

    return ':'.join(t)

  def __repr__(self):
    return self.__str__()

class ASTNode(object):
  """
  Base class of all AST nodes.

  :param SourceLocation location: location of the node in the input stream.
  """

  __slots__ = ('children', 'location')

  def __init__(self, location = None):
    self.children = []
    self.location = location

class FileNode(ASTNode):
  """
  One translation unit, usualy one assembly file.

  :param str filepath: path to the file.
  """

  __slots__ = ASTNode.__slots__ + ('filepath',)

  def __init__(self, filepath, *args, **kwargs):
    super(FileNode, self).__init__(*args, **kwargs)

    self.filepath = filepath

  def __repr__(self):
    return '<File: filepath=%s>' % self.filepath

class LabelNode(ASTNode):
  """
  Represents a label in instruction stream.

  :param str name: label.
  """

  __slots__ = ASTNode.__slots__ + ('name',)

  def __init__(self, name, *args, **kwargs):
    super(LabelNode, self).__init__(*args, **kwargs)

    self.name = name

  def __repr__(self):
    return '<Label: name="%s">' % self.name

class DirectiveNode(ASTNode):
  """
  Base class of nodes representing assembler directives.
  """

  pass

class SetDirectiveNode(ASTNode):
  __slots__ = ASTNode.__slots__ + ('name', 'value')

  def __init__(self, name, value, *args, **kwargs):
    super(SetDirectiveNode, self).__init__(*args, **kwargs)

    self.name = name
    self.value = value

  def __repr__(self):
    return '<%s: name=%s, value=%s>' % (self.__class__.__name__, self.name, self.value)

class GlobalDirectiveNode(DirectiveNode):
  """
  ``.global`` directive.

  :param str name: symbol name.
  """

  __slots__ = DirectiveNode.__slots__ + ('name',)

  def __init__(self, name, *args, **kwargs):
    super(GlobalDirectiveNode, self).__init__(*args, **kwargs)

    self.name = name

  def __repr__(self):
    return '<GlobalDirective: name=%s>' % self.name

class FileDirectiveNode(DirectiveNode):
  """
  ``.file`` directive.

  :param str filepath: path to the file.
  """

  __slots__ = DirectiveNode.__slots__ + ('filepath',)

  def __init__(self, filepath, *args, **kwargs):
    super(FileDirectiveNode, self).__init__(*args, **kwargs)

    self.filepath = filepath

  def __repr__(self):
    return '<FileDirective: filepath=%s>' % self.filepath

class SectionDirectiveNode(DirectiveNode):
  """
  ``.section`` directive.

  :param str name: section name.
  """

  __slots__ = DirectiveNode.__slots__ + ('name', 'flags')

  def __init__(self, name, flags, *args, **kwargs):
    super(SectionDirectiveNode, self).__init__(*args, **kwargs)

    self.name = name
    self.flags = flags

  def __repr__(self):
    return '<SectionDirective: name=%s, flags=%s>' % (self.name, self.flags)

class DataSectionDirectiveNode(SectionDirectiveNode):
  """
  ``.data`` section.
  """

  def __init__(self, *args, **kwargs):
    super(DataSectionDirectiveNode, self).__init__('.data', None, *args, **kwargs)

class TextSectionDirectiveNode(SectionDirectiveNode):
  """
  ``.text`` directive.
  """

  def __init__(self, *args, **kwargs):
    super(TextSectionDirectiveNode, self).__init__('.text', None, *args, **kwargs)

class SlotNode(ASTNode):
  __slots__ = ASTNode.__slots__ + ('value',)

  def __init__(self, value, *args, **kwargs):
    super(SlotNode, self).__init__(*args, **kwargs)

    self.value = value

  def __repr__(self):
    return '<%s: value="%s">' % (self.__class__.__name__, self.value)

class StringNode(SlotNode):
  def __init__(self, value, *args, **kwargs):
    super(StringNode, self).__init__(value, *args, **kwargs)

    self.value = value[1:-1]

class AsciiNode(SlotNode):
  def __init__(self, value, *args, **kwargs):
    super(AsciiNode, self).__init__(value, *args, **kwargs)

    self.value = value[1:-1]

class SpaceNode(SlotNode):
  pass

class AlignNode(SlotNode):
  pass

class ByteNode(SlotNode):
  pass

class ShortNode(SlotNode):
  pass

class WordNode(SlotNode):
  pass


class Operand(object):
  """
  Base class of all operand classes.

  :param operand: the actual operand.
  """

  __slots__ = ('operand',)

  def __init__(self, operand):
    self.operand = operand

  def __repr__(self):
    return '<%s %s>' % (self.__class__.__name__, self.operand)

class RegisterOperand(Operand):
  pass

class ImmediateOperand(Operand):
  pass

class ReferenceOperand(ImmediateOperand):
  pass

class BOOperand(Operand):
  def __init__(self, base, offset):
    super(BOOperand, self).__init__((base, offset))

class InstructionNode(ASTNode):
  __slots__ = ASTNode.__slots__ + ('instr', 'operands')

  def __init__(self, instr, operands, *args, **kwargs):
    super(InstructionNode, self).__init__(*args, **kwargs)

    self.instr = instr
    self.operands = operands

  def __repr__(self):
    return '<Instruction: %s (%s)>' % (self.instr, ', '.join([repr(operand) for operand in self.operands]))
