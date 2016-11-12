import collections
import ctypes
import functools
import os.path
import subprocess

from six import iteritems, itervalues, integer_types, PY2
from six.moves import UserDict

from .lexer import AssemblyLexer
from .parser import AssemblyParser
from .ast import FileNode, LabelNode, GlobalDirectiveNode, FileDirectiveNode, SectionDirectiveNode, DataSectionDirectiveNode, TextSectionDirectiveNode, SetDirectiveNode
from .ast import StringNode, AsciiNode, SpaceNode, AlignNode, ByteNode, ShortNode, WordNode, InstructionNode, SourceLocation, ExpressionNode

from ..cpu.instructions import EncodingContext, encoding_to_u32

from .. import cpu
from .. import mm
from ..cpu.coprocessor.math_copro import MathCoprocessorInstructionSet  # noqa - it's not unused, SIS instruction may need it but that's hidden from flake

from ..mm import PAGE_SIZE, UINT32_FMT
from ..mm.binary import SectionTypes, SectionFlags, RelocFlags
from ..util import align, LoggingCapable, str2bytes, bytes2str
from ..errors import ConflictingNamesError, UnknownInstructionError

from functools import partial
from collections import OrderedDict

align_to_next_page = functools.partial(align, PAGE_SIZE)

if PY2:
  def decode_string(s):
    return s.decode('string_escape')

else:
  def decode_string(s):
    return str2bytes(s).decode('unicode_escape')

class Section(object):
  __slots__ = ('name', 'type', 'flags', 'content', 'base', 'ptr')

  def __init__(self, s_name, s_type = SectionTypes.PROGBITS, s_flags = None):
    super(Section, self).__init__()

    self.name    = s_name
    self.type    = s_type
    self.flags   = SectionFlags.from_int(0) if s_flags is None else SectionFlags.from_string(s_flags)
    self.content = []

    self.base = 0
    self.ptr  = 0

  def __getattr__(self, name):
    if name == 'data_size':
      return self.ptr - self.base

    if name == 'file_size':
      if self.flags.bss is True:
        return 0

      return self.data_size

  def __repr__(self):
    return '<Section: name=%s, type=%s, flags=%s, base=%s, ptr=%s, data_size=%s, file_size=%s>' % (self.name, self.type, self.flags.to_string(), UINT32_FMT(self.base) if self.base is not None else '', UINT32_FMT(self.ptr), self.data_size, self.file_size)

class SymtabSection(Section):
  def __init__(self):
    super(SymtabSection, self).__init__('.symtab', s_type = SectionTypes.SYMBOLS)

class RelocSection(Section):
  def __init__(self):
    super(RelocSection, self).__init__('.reloc', s_type = SectionTypes.RELOC)

class Label(object):
  __slots__ = ('name', 'section', 'location', 'globally_visible')

  def __init__(self, name, section, location):
    super(Label, self).__init__()

    self.name = name
    self.section = section
    self.location = location

    self.globally_visible = False

  def __repr__(self):
      return '<label %s:%s>' % (self.section.name, self.name)

class Slot(object):
  """
  Base class of all items the sections can contain.
  """

  __slots__ = ('ctx', 'size', 'value', 'refers_to', 'section', 'section_ptr', 'location', 'labels')

  def __init__(self, ctx, size = None, value = None, section = None, section_ptr = None, location = None, labels = None):
    self.ctx = ctx

    if size is not None:
      self.size = size

    self.value     = value
    self.refers_to = None

    self.section = section
    self.section_ptr = section_ptr

    self.location = location.copy() if location is not None else None
    self.labels = labels or []

  def __repr__(self):
    d = OrderedDict()
    d['size'] = str(self.size)
    d['section'] = self.section.name

    if self.refers_to is not None:
      d['refers_to'] = self.refers_to

    if self.value is not None:
      d['value'] = self.value

    if self.labels:
      d['labels'] = ', '.join(['%s:%s' % (l.section.name, l.name) for l in self.labels])

    return '<%s: %s>' % (self.__class__.__name__, ', '.join(['%s=%s' % (k, v) for k, v in iteritems(d)]))

  def place_in_section(self, section, sections, references):
    pass

  def resolve_reference(self, section, sections, references):
    raise NotImplementedError()

  def do_finalize_value(self):
    pass

  def finalize_value(self):
    assert self.section is not None

    if self.section.flags.bss is True:
      if self.value is not None and any((b != 0 for b in self.value)):
        self.ctx.WARN('%s: Slot has non-zero initial value that will be lost since it is located in BSS section', self.location)

      self.value = None
      return

    self.do_finalize_value()

class RelocSlot(object):
  __slots__ = ('name', 'flags', 'patch_section', 'patch_address', 'patch_offset', 'patch_size', 'patch_add', 'size')

  def __init__(self, name, flags = None, patch_section = None, patch_address = None, patch_offset = None, patch_size = None, patch_add = None):
    super(RelocSlot, self).__init__()

    self.name = name
    self.flags = flags or RelocFlags.create()
    self.patch_section = patch_section
    self.patch_address = patch_address
    self.patch_offset = patch_offset
    self.patch_size = patch_size
    self.patch_add = patch_add

    self.size = 0

  def __repr__(self):
    return '<RelocSlot: name=%s, flags=%s, section=%s, address=%s, offset=%s, size=%s, add=%s>' % (self.name, self.flags.to_string(), self.patch_section, UINT32_FMT(self.patch_address), self.patch_offset, self.patch_size, self.patch_add)

class Reference(object):
  __slots__ = ('refers_to',)

  def __init__(self, refers_to):
    self.refers_to = refers_to

  def __repr__(self):
    return '<%s: refers to "%s">' % (self.__class__.__name__, self.refers_to)

class NumberPayloadSlot(Slot):
  def unpack_value(self):
    raise NotImplementedError()

  def __init__(self, *args, **kwargs):
    super(NumberPayloadSlot, self).__init__(*args, **kwargs)

    assert isinstance(self.value, ExpressionNode), repr(self.value)

    if self.value.is_int():
      self.unpack_value()

    else:
      self.refers_to = Reference(self.value)
      self.value = None

  def resolve_reference(self, section, sections, references):
    assert self.refers_to is not None

    reference, self.refers_to = self.refers_to.refers_to, None

    if reference.is_str():
      re = RelocSlot(reference.value, flags = RelocFlags.create(relative = False, inst_aligned = False),
                     patch_section = section, patch_address = section.ptr, patch_size = self.size * 8, patch_offset = 0)
    else:
      lh, op, rh = reference.value

      if rh.is_str():
        lh, rh = rh, lh

      assert lh.is_str()
      assert rh.is_int()
      assert op == '+'

      re = RelocSlot(lh.value, flags = RelocFlags.create(relative = False, inst_aligned = False),
                     patch_section = section, patch_address = section.ptr, patch_size = self.size * 8, patch_offset = 0, patch_add = rh.value)

    sections['.reloc'].content.append(re)

    self.value = [0x79] * self.size

class ByteSlot(NumberPayloadSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR
  size = 1

  def unpack_value(self):
    self.value = [(self.value.value & 0xFF) or 0]

class ShortSlot(NumberPayloadSlot):
  symbol_type = mm.binary.SymbolDataTypes.SHORT
  size = 2

  def unpack_value(self):
    v = self.value.value
    self.value = [v & 0xFF, (v >> 8) & 0xFF]

class WordSlot(NumberPayloadSlot):
  symbol_type = mm.binary.SymbolDataTypes.INT
  size = 4

  def unpack_value(self):
    v = self.value.value
    self.value = [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]

class CharSlot(NumberPayloadSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR
  size = 1

  def unpack_value(self):
    self.value = [ord(self.value or '\0') & 0xFF]

class SpaceSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def __init__(self, *args, **kwargs):
    super(SpaceSlot, self).__init__(*args, **kwargs)

    self.size = self.value
    self.value = None

  def finalize_value(self):
    if self.section.flags.bss is False:
      self.value = [0 for _ in range(0, self.size)]

class AsciiSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def __init__(self, *args, **kwargs):
    super(AsciiSlot, self).__init__(*args, **kwargs)

    v = decode_string(self.value) or ''
    self.value = [ord(c) & 0xFF for c in v]
    self.size = len(self.value)

class StringSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.STRING

  def __init__(self, *args, **kwargs):
    super(StringSlot, self).__init__(*args, **kwargs)

    v = decode_string(self.value) or ''
    self.value = [ord(c) & 0xFF for c in v] + [0]
    self.size = len(self.value)

class BytesSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def __init__(self, *args, **kwargs):
    super(BytesSlot, self).__init__(*args, **kwargs)

    v = self.value or ''
    self.value = [b & 0xFF for b in v]
    self.size = len(self.value)

class AlignSlot(Slot):
  size = 0

  def place_in_section(self, section, sections, references):
    assert isinstance(self.value, ExpressionNode)
    assert self.value.is_int()

    aligned_ptr = align(self.value.value, section.ptr)

    self.size = aligned_ptr - section.ptr
    self.value = [0] * self.size

class FunctionSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION
  size = 0

class InstrSlot(Slot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION
  size = 4

  def resolve_reference(self, section, sections, references):
    assert self.refers_to is not None

    instr = self.value

    reference, instr.refers_to = instr.refers_to, None

    reloc = RelocSlot(reference.operand, flags = RelocFlags.create(relative = instr.desc.relative_address, inst_aligned = instr.desc.inst_aligned), patch_section = section, patch_address = section.ptr)
    instr.fill_reloc_slot(instr, reloc)

    sections['.reloc'].content.append(reloc)

  def place_in_section(self, section, sections, references):
    # labels in data sections were handled by their parenting slots,
    # for labels in text sections we must create necessary slots

    for label in self.labels:
      slot = FunctionSlot(ctx = self.ctx, labels = [label], section = section, section_ptr = section.ptr, location = label.location)

      sections['.symtab'].content.append(slot)

  def finalize_value(self):
    v = encoding_to_u32(self.value)

    self.value = [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]

class SymbolList(UserDict):
  def __init__(self, ctx):
    UserDict.__init__(self)

    self._ctx = ctx

  def touch(self, name, loc):
    if name in self.data:
      raise self._ctx.get_error(ConflictingNamesError, name = name, prev_location = self.data[name])

    self.data[name] = loc

def sizeof(o):
  if isinstance(o, RelocSlot):
    return 0

  if isinstance(o, Slot):
    return o.size

  if isinstance(o, ctypes.LittleEndianStructure):
    return ctypes.sizeof(o)

  if isinstance(o, integer_types):
    return 1

  return ctypes.sizeof(o)

class AssemblerProcess(LoggingCapable, object):
  def __init__(self, filepath, base_address = None, writable_sections = False, defines = None, includes = None, logger = None):
    super(AssemblerProcess, self).__init__(logger)

    self._filepath = filepath

    self.base_address = base_address or 0x00000000
    self.defines = defines or {}
    self.includes = includes or []

    self.preprocessed = None

    self.ast_root = None

    self.sections_pass1 = None
    self.labels = None
    self.global_symbols = None

    self.sections_pass2 = None

    self.includes.insert(0, os.getcwd())

  def get_error(self, cls, location = None, **kwargs):
    kwargs['location'] = location.copy()

    return cls(**kwargs)

  def preprocess(self):
    includes = ['-I %s' % i for i in self.includes]
    defines = ['-D%s' % i for i in self.defines]

    cmd = '/usr/bin/cpp %s %s %s' % (' '.join(includes), ' '.join(defines), self._filepath)

    self.preprocessed = bytes2str(subprocess.check_output(cmd, shell = True))

  def parse(self):
    assert self.preprocessed is not None

    self.ast_root = FileNode(self._filepath)

    lexer = AssemblyLexer()
    parser = AssemblyParser(lexer, logger = self._logger)

    parser.parse(self.preprocessed, self.ast_root)

  def pass1(self):
    """
    Pass #1 transforms list of AST nodes into a multiple lists of Slots,
    grouped by sections. It preserves necessary information for later
    resolution of slots referencing each other. Also, list of known
    labels is created.
    """

    assert self.ast_root is not None

    class Context(object):
      curr_section    = None
      labels          = []
      instruction_set = cpu.instructions.DuckyInstructionSet

    D = self.DEBUG

    D('Pass #1')

    sections = collections.OrderedDict([
      ('.text',    Section('.text', s_flags = 'lrx')),
      ('.data',    Section('.data', s_flags = 'lrw')),
      ('.rodata',  Section('.rodata', s_flags = 'lr')),
      ('.bss',     Section('.bss',    s_flags = 'lrwb')),
      ('.symtab',  SymtabSection()),
      ('.reloc',   RelocSection())
    ])

    ctx = Context()
    encoder = EncodingContext(self._logger)

    symbols = SymbolList(self)
    global_symbols = []
    variables = {}
    labels = {}

    D('Pass #1: text section is .text')
    D('Pass #1: data section is .data')

    ctx.curr_section = sections['.text']

    location = SourceLocation(filename = self._filepath, lineno = 0)

    def __handle_section_directive(node):
      s_name = node.name

      if s_name not in sections:
        if node.flags is None:
          self.WARN('%s: Unspecified flags for section %s, using "RL" as defaults', node.location, s_name)
          flags = 'rl'

        else:
          flags = node.flags

        section = sections[s_name] = Section(s_name, s_type = SectionTypes.PROGBITS, s_flags = flags)
        D(msg_prefix + 'section created: %s', section)

      ctx.curr_section = sections[s_name]

      D(msg_prefix + 'current section is %s', ctx.curr_section.name)

    def __handle_data_directive(node):
      ctx.curr_section = sections['.data']
      D(msg_prefix + 'current section is %s', ctx.curr_section.name)

    def __handle_text_directive(node):
      ctx.curr_section = sections['.text']
      D(msg_prefix + 'current section is %s', ctx.curr_section.name)

    def __handle_file_directive(node):
      location.filename = node.filepath

    def __do_handle_slot_definition(slot_klass, node):
      value = node.value

      if isinstance(value, ExpressionNode) and value.is_str():
        if value.value in variables:
          value.value = variables.get(value.value)

      slot = slot_klass(ctx = self, section = ctx.curr_section, location = node.location, labels = ctx.labels, value = value)

      D(msg_prefix + str(slot))

      ctx.curr_section.content.append(slot)

      for label in ctx.labels:
        labels[label.name] = slot

      ctx.labels = []

    def __handle_global_directive(node):
      global_symbols.append(node.name)

    def __handle_label(node):
      label = Label(node.name, ctx.curr_section, node.location)

      symbols.touch(node.name, node.location)
      ctx.labels.append(label)

    def __handle_instruction(node):
      D(msg_prefix + 'instr set: %s', ctx.instruction_set)

      for desc in ctx.instruction_set.instructions:
        if desc.mnemonic != node.instr:
          continue
        break

      else:
        raise self.get_error(UnknownInstructionError, location = node.location)

      emited_inst = desc.emit_instruction(encoder, desc, node.operands)
      emited_inst.desc = desc

      slot = InstrSlot(ctx = self, section = ctx.curr_section, labels = ctx.labels, value = emited_inst, location = node.location)
      if hasattr(emited_inst, 'refers_to') and emited_inst.refers_to is not None:
        slot.refers_to = emited_inst.refers_to

      ctx.curr_section.content.append(slot)

      for label in ctx.labels:
        labels[label.name] = slot

      ctx.labels = []

      emited_inst_disassemble = emited_inst.desc.instruction_set.disassemble_instruction(self._logger, emited_inst)
      D(msg_prefix + 'emitted instruction: %s (%s)', emited_inst_disassemble, UINT32_FMT(encoding_to_u32(emited_inst)))

      if isinstance(desc, cpu.instructions.SIS):
        D(msg_prefix + 'switching istruction set: inst_set=%s', emited_inst.immediate)

        ctx.instruction_set = cpu.instructions.get_instruction_set(emited_inst.immediate)

    def __handle_set_directive(node):
      name = node.name

      if node.value == '.':
        value = (ctx.curr_section.name, ctx.curr_section.ptr)

      else:
        value = node.value

      D(msg_prefix + 'set variable: name=%s, value=%s', name, value)
      variables[name] = value

    handler_map = {
      DataSectionDirectiveNode:    __handle_data_directive,
      TextSectionDirectiveNode:    __handle_text_directive,
      SectionDirectiveNode: __handle_section_directive,
      FileDirectiveNode:    __handle_file_directive,
      GlobalDirectiveNode:  __handle_global_directive,
      SetDirectiveNode:     __handle_set_directive,

      LabelNode:              __handle_label,
      ByteNode:      partial(__do_handle_slot_definition, ByteSlot),
      ShortNode:     partial(__do_handle_slot_definition, ShortSlot),
      WordNode:      partial(__do_handle_slot_definition, WordSlot),
      StringNode:    partial(__do_handle_slot_definition, StringSlot),
      AsciiNode:     partial(__do_handle_slot_definition, AsciiSlot),
      SpaceNode:     partial(__do_handle_slot_definition, SpaceSlot),
      AlignNode:     partial(__do_handle_slot_definition, AlignSlot),

      InstructionNode:        __handle_instruction
    }

    for node in self.ast_root.children:
      msg_prefix = 'pass #1: %s: ' % node.location
      D(msg_prefix + str(node))

      handler_map[node.__class__](node)

    for section in itervalues(sections):
      D('pass #1: %s', section)

      for slot in section.content:
        D('pass #1: %s', slot)

    self.sections_pass1 = sections
    self.labels = labels
    self.global_symbols = global_symbols

  def pass2(self):
    assert self.sections_pass1 is not None

    D = self.DEBUG

    D('Pass #2')

    sections = collections.OrderedDict()
    base_ptr = self.base_address

    for s_name, p1_section in iteritems(self.sections_pass1):
      sections[s_name] = Section(s_name, s_type = p1_section.type, s_flags = p1_section.flags.to_string())

    symtab = sections['.symtab']

    for s_name, section in iteritems(sections):
      p1_section = self.sections_pass1[s_name]

      section.base = base_ptr
      section.ptr  = base_ptr

      D('pass #2: section %s - base=%s', section.name, UINT32_FMT(section.base))
      D('pass #2: %s', section)

      if section.type != SectionTypes.PROGBITS:
        continue

      for slot in p1_section.content:
        msg_prefix = 'pass #2: ' + UINT32_FMT(section.ptr) + ': '

        assert slot.section is not None
        assert slot.section == p1_section

        D(msg_prefix + str(slot))

        slot.section = section
        slot.section_ptr = section.ptr

        if slot.labels and not isinstance(slot, InstrSlot):
          symtab.content.append(slot)

        if slot.refers_to is not None:
          slot.resolve_reference(section, sections, self.labels)

        slot.place_in_section(section, sections, self.labels)

        section.content.append(slot)
        section.ptr += slot.size

      base_ptr = align_to_next_page(section.ptr)

    for section in itervalues(sections):
      D('pass #2: %s', section)

      for slot in section.content:
        D('pass #2: %s', slot)

    self.sections_pass2 = sections

  def pass3(self):
    D = self.DEBUG

    D('Pass #3')

    sections = {}

    for s_name, p2_section in iteritems(self.sections_pass2):
      sections[s_name] = Section(s_name, s_type = p2_section.type, s_flags = p2_section.flags.to_string())

    sections['.symtab'] = self.sections_pass2['.symtab']
    sections['.reloc'] = self.sections_pass2['.reloc']

    for s_name, section in iteritems(sections):
      D('pass #3: %s', section)

      p2_section = self.sections_pass2[s_name]

      if section.type == SectionTypes.SYMBOLS:
        for slot in p2_section.content:
          for label in slot.labels:
            if label.name in self.global_symbols:
              label.globally_visible = True

        continue

      if section.type != SectionTypes.PROGBITS:
        continue

      section.base = p2_section.base
      section.ptr  = section.base

      for slot in p2_section.content:
        msg_prefix = 'pass #3: ' + UINT32_FMT(section.ptr) + ': '

        D(msg_prefix + str(slot))

        slot.section = section
        assert slot.section_ptr == section.ptr

        slot.finalize_value()

        if section.flags.bss is True:
          assert slot.value is None

        else:
          assert isinstance(slot.value, list), '%s: invalid value - list expected, %s found' % (slot, type(slot.value))

          section.content += slot.value

        section.ptr += slot.size

      assert p2_section.ptr == section.ptr

      section.content = bytearray(section.content)

    D('')
    D('** Pass #3 finished:')
    D('')
    for section in itervalues(sections):
      D('pass #3: %s', section)

      for i in section.content:
        D('pass #3: %s', i)

    self.sections_pass3 = sections

  def translate(self):
    self.preprocess()
    self.parse()
    self.pass1()
    self.pass2()
    self.pass3()
