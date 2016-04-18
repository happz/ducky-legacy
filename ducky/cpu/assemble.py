import collections
import ctypes
import functools
import mmap
import os.path
import re

from six import iteritems, itervalues, integer_types, string_types, PY2

from .. import cpu
from .. import mm
from ..cpu.coprocessor.math_copro import MathCoprocessorInstructionSet  # noqa - it's not unused, SIS instruction may need it but that's hidden from flake
from ..cpu.instructions import encoding_to_u32

from ..mm import u8_t, PAGE_SIZE, UINT32_FMT
from ..mm.binary import SectionTypes, SectionFlags, SymbolFlags, RelocFlags
from ..util import align, str2bytes
from ..errors import AssemblerError, IncompleteDirectiveError, UnknownFileError, DisassembleMismatchError, UnknownPatternError, TooManyLabelsError

align_to_next_page = functools.partial(align, PAGE_SIZE)
align_to_next_mmap = functools.partial(align, mmap.PAGESIZE)

def PATTERN(pattern):
  return re.compile(r'^\s*(?P<payload>' + pattern + r')(?:\s*[;#].*)?$', re.MULTILINE)

RE_INTEGER = re.compile(r'^\s+(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_var>[a-zA-Z][a-zA-Z0-9_]*(?:.*?)?)|(?P<value_label>&[a-zA-Z_\.][a-zA-Z0-9_\.]*))\s*$')
RE_STR = re.compile(r'^\s*"(?P<string>.*?)"\s*$')

RE_COMMENT = re.compile(r'^\s*[/;].*?$', re.MULTILINE)
RE_INCLUDE = PATTERN(r'\.include\s+"(?P<file>[a-zA-Z0-9_\-/\.]+)\s*"')
RE_IFDEF = PATTERN(r'.ifdef\s+(?P<var>[a-zA-Z0-9_]+)$')
RE_IFNDEF = PATTERN(r'\.ifndef\s+(?P<var>[a-zA-Z0-9_]+)')
RE_ELSE = PATTERN(r'\.else')
RE_ENDIF = PATTERN(r'\.endif')
RE_VAR_DEF = PATTERN(r'\.def\s+(?P<var_name>[a-zA-Z][a-zA-Z0-9_]*):\s*(?P<var_body>.*?)')
RE_MACRO_DEF = re.compile(r'^\s*\.macro\s+(?P<macro_name>[a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?P<macro_params>.*?))?:$', re.MULTILINE | re.DOTALL)
RE_MACRO_END = PATTERN(r'\.end')
RE_ASCII = PATTERN(r'\.ascii\s+(?P<string>".*?")')
RE_BYTE = PATTERN(r'\.byte(?P<integer>.*?)')
RE_DATA = PATTERN(r'\.data(?:\s+(?P<name>\.[a-z][a-z0-9_]*))?')
RE_INT = PATTERN(r'\.int(?P<integer>.*?)')
RE_LABEL = PATTERN(r'(?P<label>[a-zA-Z_\.][a-zA-Z0-9_\.]*):')
RE_SECTION = PATTERN(r'\.section\s+(?P<name>\.[a-zA-z0-9_]+)(?:,\s*(?P<flags>[rwxlbmg]*))?')
RE_SET = PATTERN(r'\.set\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?:(?P<current>\.)|(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_label>&[a-zA-Z][a-zA-Z0-9_]*))')
RE_SHORT = PATTERN(r'\.short(?P<integer>.*?)')
RE_SIZE = PATTERN(r'\.size\s+(?P<size>[1-9][0-9]*)')
RE_SPACE = PATTERN(r'\.space\s+(?P<size>[1-9][0-9]*)')
RE_STRING = PATTERN(r'\.string(?P<string>.*?)')
RE_TEXT = PATTERN(r'\.text(?:\s+(?P<name>\.[a-z][a-z0-9_]*))?')
RE_TYPE = PATTERN(r'\.type\s+(?P<name>[a-zA-Z_\.][a-zA-Z0-9_]*),\s*(?P<type>(?:char|byte|short|int|ascii|string|space))')
RE_GLOBAL = PATTERN(r'\.global\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)')
RE_ALIGN  = PATTERN(r'\.align\s+(?P<boundary>[0-9]+)')

class SourceLocation(object):
  def __init__(self, filename = None, lineno = None, column = None, length = None):
    self.filename = filename
    self.lineno = lineno
    self.column = column
    self.length = length

  def copy(self):
    return SourceLocation(filename = self.filename, lineno = self.lineno, column = self.column, length = self.length)

  def __str__(self):
    t = [self.filename, str(self.lineno)]
    if self.column is not None:
      t.append(str(self.column))
    return ':'.join(t)

  def __repr__(self):
    return str(self)

class Buffer(object):
  def __init__(self, logger, filename, buff):
    super(Buffer, self).__init__()

    self.logger = logger
    self.DEBUG = logger.debug
    self.INFO = logger.info
    self.WARN = logger.warning
    self.ERROR = logger.error
    self.EXCEPTION = logger.exception

    self.buff = buff

    self.location = SourceLocation(filename = filename, lineno = 0)
    self.last_line = None

  def get_line(self):
    while self.buff:
      self.location.lineno += 1

      line = self.buff.pop(0)

      if isinstance(line, SourceLocation):
        self.location = line

        self.DEBUG('buffer: file switch: %s', str(self.location))
        continue

      if not line:
        continue

      self.DEBUG('buffer: new line %s: %s', str(self.location), line)
      self.last_line = line
      return line

    self.last_line = None
    return None

  def put_line(self, line):
    self.buff.insert(0, line)
    self.location.lineno -= 1

  def put_buffer(self, buff, filename = None):
    filename = filename or '<unknown>'

    self.buff.insert(0, self.location.copy())

    if isinstance(buff, string_types):
      buff = buff.split('\n')

    for line in reversed(buff):
      self.buff.insert(0, line)

    self.buff.insert(0, SourceLocation(filename = filename, lineno = 0))

  def has_lines(self):
    return len(self.buff) > 0

  def get_error(self, cls, info, column = None, length = None, **kwargs):
    location = self.location.copy()
    location.column = column
    location.length = length

    kwargs['location'] = location
    if 'line' not in kwargs:
      kwargs['line'] = self.last_line

    kwargs['info'] = info

    return cls(**kwargs)

class Section(object):
  def __init__(self, s_name, s_type, s_flags):
    super(Section, self).__init__()

    self.name    = s_name
    self.type    = s_type
    self.flags   = s_flags
    self.content = []

    self.base = None
    self.ptr  = 0

  def __getattr__(self, name):
    if name == 'data_size':
      return sum([sizeof(i) for i in self.content])

    if name == 'file_size':
      return align_to_next_mmap(self.data_size) if self.flags.mmapable == 1 else self.data_size

    if name == 'items':
      return len(self.content)

  def __repr__(self):
    return '<Section: name=%s, type=%s, flags=%s, base=%s, ptr=%s, items=%s, data_size=%s, file_size=%s>' % (self.name, self.type, self.flags.to_string(), UINT32_FMT(self.base), UINT32_FMT(self.ptr), self.items, self.data_size, self.file_size)

class TextSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(TextSection, self).__init__(s_name, SectionTypes.TEXT, flags or SectionFlags.create(readable = True, executable = True, loadable = True))

class RODataSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(RODataSection, self).__init__(s_name, SectionTypes.DATA, flags or SectionFlags.create(readable = True, loadable = True))

class DataSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(DataSection, self).__init__(s_name, SectionTypes.DATA, flags or SectionFlags.create(readable = True, writable = True, loadable = True))

class BssSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(BssSection, self).__init__(s_name, SectionTypes.DATA, flags or SectionFlags.create(readable = True, writable = True, loadable = True, bss = True))

class SymbolsSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(SymbolsSection, self).__init__(s_name, SectionTypes.SYMBOLS, SectionFlags.create())

class RelocSection(Section):
  def __init__(self, s_name, flags = None, **kwargs):
    super(RelocSection, self).__init__(s_name, SectionTypes.RELOC, SectionFlags.create())

class Label(object):
  def __init__(self, name, section, location):
    super(Label, self).__init__()

    self.name = name
    self.section = section
    self.location = location

  def __repr__(self):
    return '<label {} in section {} ({})>'.format(self.name, self.section.name if self.section else None, str(self.location))

class Reference(object):
  def __init__(self, add = None, label = None):
    self.add = add or 0
    self.label = label

  def __repr__(self):
    return '<Reference: label=%s, add=%s>' % (self.label, self.add)

class RelocSlot(object):
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

class DataSlot(object):
  def __init__(self):
    super(DataSlot, self).__init__()

    self.name  = None
    self.size  = None
    self.refers_to = None
    self.value = None

    self.flags = SymbolFlags.create()

    self.section = None
    self.section_ptr = None

    self.location = None

  def close(self):
    pass

class ByteSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR

  def close(self):
    self.size = 1

    if self.refers_to:
      return

    self.value = [u8_t(self.value or 0)]

  def __repr__(self):
    return '<ByteSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class ShortSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.SHORT

  def close(self):
    self.size = 2

    if self.refers_to:
      return

    value = self.value or 0
    self.value = [u8_t(value), u8_t(value >> 8)]

  def __repr__(self):
    return '<ShortSlot: name={}, size={}, section={}, value={}, refers_to={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value, self.refers_to)

class IntSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.INT

  def close(self):
    self.size = 4

    if self.refers_to:
      return

    value = self.value or 0
    self.value = [u8_t(value), u8_t(value >> 8), u8_t(value >> 16), u8_t(value >> 24)]

  def __repr__(self):
    return '<IntSlot: name={}, size={}, section={}, value={}, refers_to={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value, self.refers_to)

class CharSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR

  def close(self):
    self.size = 1
    self.value = u8_t(ord(self.value or '\0'))

  def __repr__(self):
    return '<CharSlot: name={}, section={}, value={}>'.format(self.name, self.section.name if self.section else '', self.value)

class SpaceSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = None
    self.size = self.size

  def __repr__(self):
    return '<SpaceSlot: name={}, size={}, section={}>'.format(self.name, self.size, self.section.name if self.section else '')

class AsciiSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = self.value or ''
    self.value = [u8_t(ord(c)) for c in self.value]
    self.size = len(self.value)

  def __repr__(self):
    return '<AsciiSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class StringSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.STRING

  def close(self):
    self.value = self.value or ''
    self.value = [u8_t(ord(c)) for c in self.value] + [u8_t(0)]
    self.size = len(self.value)

  def __repr__(self):
    return '<StringSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class BytesSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = self.value or ''
    self.value = [u8_t(b) for b in self.value]
    self.size = len(self.value)

  def __repr__(self):
    return '<BytesSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class AlignSlot(DataSlot):
  def __init__(self, boundary):
    super(AlignSlot, self).__init__()

    self.boundary = boundary

  def __repr__(self):
    return '<AlignSlot: boundary={}>'.format(self.boundary)

class FunctionSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION

  def close(self):
    self.size = 0

  def __repr__(self):
    return '<FunctionSlot: name={}, section={}>'.format(self.name, self.section.name if self.section else '')

def sizeof(o):
  if isinstance(o, RelocSlot):
    return 0

  if isinstance(o, DataSlot):
    return o.size

  if isinstance(o, ctypes.LittleEndianStructure):
    return ctypes.sizeof(o)

  return ctypes.sizeof(o)

if PY2:
  def decode_string(s):
    return s.decode('string_escape')

else:
  def decode_string(s):
    return str2bytes(s).decode('unicode_escape')

def translate_buffer(logger, buff, base_address = None, mmapable_sections = False, writable_sections = False, filename = None, defines = None, includes = None, verify_disassemble = False):
  DEBUG = logger.debug

  base_address = base_address or 0
  filename = filename or '<unknown>'
  defines = defines or []
  includes = includes or []
  includes.insert(0, os.getcwd())

  defines = {var[0]: var[1] if len(var) > 1 else None for var in (var.split('=') for var in defines)}

  DEBUG('translate_buffer: base_addres=%s, mmapable_sections=%s, writable_sections=%s, filename=%s, defines=%s, includes=%s, verify_disassemble=%s', UINT32_FMT(base_address), mmapable_sections, writable_sections, filename, defines, includes, verify_disassemble)

  buff = Buffer(logger, filename, buff.split('\n'))

  sections_pass1 = collections.OrderedDict([
    ('.text',   TextSection('.text')),
    ('.rodata', RODataSection('.rodata')),
    ('.data',   DataSection('.data')),
    ('.bss',    BssSection('.bss')),
    ('.symtab', SymbolsSection('.symtab')),
    ('.reloc',  RelocSection('.reloc'))
  ])

  if mmapable_sections:
    for section in itervalues(sections_pass1):
      section.flags.mmapable = True

  if writable_sections:
    for section in [_section for _section in itervalues(sections_pass1) if _section.name in ('.text', '.rodata', '.data', '.bss')]:
      section.flags.writable = True

  DEBUG('Pass #1')

  labeled = []

  line = None

  def __apply_defs(line):
    orig_line = line

    for def_pattern, def_value in iteritems(defs):
      line = def_pattern.sub(def_value, line)

    if orig_line != line:
      DEBUG(msg_prefix + 'variables replaced: line="%s"', line)

    return line

  def __apply_macros(line):
    for m_pattern, m_desc in iteritems(macros):
      matches = m_pattern.match(line)
      if not matches:
        continue

      DEBUG(msg_prefix + 'replacing macro: name=%s', m_desc['name'])

      if m_desc['params']:
        matches = matches.groupdict()

        replace_map = {}
        for i in range(0, len(m_desc['params'])):
          replace_map[re.compile(r'#{}'.format(m_desc['params'][i]))] = matches['arg{}'.format(i)]

        DEBUG(msg_prefix + 'macro args: %s', ', '.join(['{} => {}'.format(pattern.pattern, repl) for pattern, repl in iteritems(replace_map)]))

        body = []
        for line in m_desc['body']:
          for pattern, repl in iteritems(replace_map):
            line = pattern.sub(repl, line)
          body.append(line)

        buff.put_buffer(body)

      else:
        buff.put_buffer(m_desc['body'])

      return True

    return False

  def __set_var_location(var, location = None):
    if var.location is None:
      if location is None:
        location = buff.location.copy()

      var.location = location

  def __set_var_label(var):
    if len(labels) > 1:
      raise buff.get_error(TooManyLabelsError, 'Too many labels', column = 0)

    var.name = labels[0] if labels else None

  def __parse_integer(var, matches, max):
    __set_var_location(var)

    groupdict = matches.groupdict()
    integer = groupdict.get('integer')

    DEBUG('__parse_integer: var=%s, max=%s, matches=%s', var, max, groupdict)

    if integer is None or not integer:
      raise buff.get_error(IncompleteDirectiveError, 'directive without a value specification', column = matches.end(1))

    integer_start = matches.start(2)

    matches = RE_INTEGER.match(integer)
    if matches is None:
      raise buff.get_error(IncompleteDirectiveError, 'directive without a meaningful value', column = integer_start)

    groupdict = matches.groupdict()
    DEBUG('__parse_integer: matches=%s', groupdict)

    v_value = groupdict.get('value_dec')
    if v_value:
      var.value = int(v_value)

      DEBUG('__parse_integer: var=%s', var)
      return

    v_value = groupdict.get('value_hex')
    if v_value:
      var.value = int(v_value, base = 16)

      DEBUG('__parse_integer: var=%s', var)
      return

    v_value = groupdict.get('value_var')
    if v_value:
      if v_value not in variables:
        raise buff.get_error(IncompleteDirectiveError, 'unknown variable named "%s"' % v_value, column = integer_start)

      variable = variables[v_value]

      DEBUG('__parse_integer: variable: variable=%s', variable)

      if isinstance(variable, integer_types):
        var.value = variable

      else:
        var.refers_to = Reference(label = variable)

      DEBUG('__parse_integer: var=%s', var)
      return

    v_value = groupdict.get('value_label')
    if v_value:
      var.refers_to = Reference(label = v_value)

      DEBUG('__parse_integer: var=%s', var)
      return

    raise buff.get_error(IncompleteDirectiveError, 'directive without a meaningful value', column = integer_start)

  def __parse_string(var, matches):
    __set_var_location(var)

    groupdict = matches.groupdict()

    string = groupdict.get('string')

    DEBUG('__parse_string: var=%s, max=%s, matches=%s', var, max, groupdict)

    if string is None or not string:
      raise buff.get_error(IncompleteDirectiveError, 'directive without a value specification', column = matches.end(1))

    string_start = matches.start(2)

    matches = RE_STR.match(string)
    if matches is None:
      raise buff.get_error(IncompleteDirectiveError, 'directive without a meaningful value', column = string_start)

    groupdict = matches.groupdict()

    v_value = groupdict.get('string')
    if not v_value:
      raise buff.get_error(IncompleteDirectiveError, 'directive without a meaningful value', column = string_start)

    v_value = __apply_defs(v_value)

    DEBUG('Pre-decode: (%s) %s', type(v_value), ', '.join([str(ord(c)) for c in v_value]))
    var.value = decode_string(v_value)
    DEBUG('Post-decode: (%s) %s', type(var.value), ', '.join([str(ord(c)) for c in var.value]))

  def __parse_space(var, matches):
    __set_var_location(var)

    matches = matches.groupdict()

    if 'size' not in matches:
      raise buff.get_error(IncompleteDirectiveError, '.size directive without a size')

    var.size = int(matches['size'])

  def __handle_symbol_variable(v_name, v_type):
    if v_type == 'char':
      var = CharSlot()

    elif v_type == 'byte':
      var = ByteSlot()

    elif v_type == 'short':
      var = ShortSlot()

    elif v_type == 'int':
      var = IntSlot()

    elif v_type == 'ascii':
      var = AsciiSlot()

    elif v_type == 'string':
      var = StringSlot()

    elif v_type == 'space':
      var = SpaceSlot()

    var.name = Label(v_name, curr_section, buff.location.copy())
    __set_var_location(var)

    while buff.has_lines() and var.value is None and var.refers_to is None:
      line = buff.get_line()

      if line is None:
        var.close()
        data_section.content.append(var)
        return

      matches = RE_COMMENT.match(line)
      if matches:
        continue

      msg_prefix = 'pass #1: %s: ' % str(buff.location)

      line = __apply_defs(line)

      if not current_macro and __apply_macros(line):
        DEBUG(msg_prefix + 'macro replaced, get fresh line')
        continue

      matches = RE_TYPE.match(line)
      if matches:
        buff.put_line(line)
        break

      matches = RE_SIZE.match(line)
      if matches:
        matches = matches.groupdict()

        if 'size' not in matches:
          raise buff.get_error(IncompleteDirectiveError, '.size directive without a size')

        var.size = int(matches['size'])
        continue

      matches = RE_SHORT.match(line)
      if matches:
        __parse_integer(var, matches, 0xFFFF)
        continue

      matches = RE_INT.match(line)
      if matches:
        __parse_integer(var, matches, 0xFFFFFFFF)
        continue

      matches = RE_ASCII.match(line)
      if matches:
        __parse_string(var, matches)
        continue

      matches = RE_STRING.match(line)
      if matches:
        __parse_string(var, matches)
        continue

      matches = RE_SPACE.match(line)
      if matches:
        __parse_space(var, matches)
        continue

      matches = RE_BYTE.match(line)
      if matches:
        __parse_integer(var, matches, 0xFF)
        continue

      buff.put_line(line)
      break

    var.close()
    data_section.content.append(var)

  labels = []
  variables = {}

  instruction_set = cpu.instructions.DuckyInstructionSet

  defs = collections.OrderedDict()

  for name, value in iteritems(defines):
    if value is None:
      continue

    defs[re.compile(r'\${}'.format(name))] = value.strip()

  macros = collections.OrderedDict()
  current_macro = None

  DEBUG('Pass #1: text section is .text')
  DEBUG('Pass #1: data section is .data')

  text_section = sections_pass1['.text']
  data_section = sections_pass1['.data']
  curr_section = text_section

  global_symbols = []

  ifs = []

  def __fast_forward():
    DEBUG(msg_prefix + 'fast forwarding')

    depth = 1

    while buff.has_lines():
      line = buff.get_line()

      if line is None:
        return

      if not line.strip():
        continue

      matches = RE_IFDEF.match(line)
      if matches:
        depth += 1
        continue

      matches = RE_IFNDEF.match(line)
      if matches:
        depth += 1
        continue

      matches = RE_ENDIF.match(line)
      if matches:
        depth -= 1
        if depth == 0:
          buff.put_line(line)
          return

      matches = RE_ELSE.match(line)
      if matches:
        depth -= 1
        if depth == 0:
          buff.put_line(line)
          return

  while buff.has_lines():
    line = buff.get_line()

    if line is None:
      break

    if not line.strip():
      continue

    msg_prefix = 'pass #1: %s: ' % str(buff.location)

    line = __apply_defs(line)

    if not current_macro and __apply_macros(line):
      DEBUG(msg_prefix + 'macro replaced, get fresh line')
      continue

    matches = RE_COMMENT.match(line)
    if matches:
      continue

    msg_prefix = 'pass #1: %s: ' % str(buff.location)

    matches = RE_IFDEF.match(line)
    if matches:
      var = matches.groupdict()['var']

      DEBUG(msg_prefix + 'ifdef %s', var)

      ifs.append((True, var))

      if var in defines:
        DEBUG(msg_prefix + 'defined, continue processing')
        continue

      __fast_forward()
      continue

    matches = RE_IFNDEF.match(line)
    if matches:
      var = matches.groupdict()['var']

      DEBUG(msg_prefix + 'ifndef %s', var)

      ifs.append((False, var))

      if var not in defines:
        DEBUG(msg_prefix + 'not defined, continue processing')
        continue

      __fast_forward()
      continue

    matches = RE_ENDIF.match(line)
    if matches:
      DEBUG(msg_prefix + 'removing the last conditional from stack: %s', ifs[-1])

      ifs.pop()
      continue

    matches = RE_ELSE.match(line)
    if matches:
      defined, var = ifs.pop()

      DEBUG(msg_prefix + 'previous block was "%s %s"', 'ifdef' if defined is True else 'ifndef', var)

      ifs.append((not defined, var))

      if defined and var in defines:
        __fast_forward()
        continue

      DEBUG(msg_prefix + 'continue processing')
      continue

    matches = RE_INCLUDE.match(line)
    if matches:
      groupdict = matches.groupdict()

      if 'file' not in groupdict:
        raise buff.get_error(IncompleteDirectiveError, '.include directive without path', column = 0)

      DEBUG(msg_prefix + 'include: file=%s', groupdict['file'])

      replace = None

      for d in includes:
        filename = os.path.join(d, groupdict['file'])
        DEBUG(msg_prefix + '  checking file %s', filename)

        try:
          with open(filename, 'r') as f_in:
            replace = f_in.read()

        except IOError:
          DEBUG('    failed to read')
          pass  # "empty body on ExceptHandler" without this, because of patching

        else:
          DEBUG('    read as replacement')
          break

      if replace is None:
        raise buff.get_error(UnknownFileError, groupdict['file'], column = matches.start(2))

      buff.put_buffer(replace, filename = filename)

      continue

    matches = RE_VAR_DEF.match(line)
    if matches:
      matches = matches.groupdict()

      v_name = matches.get('var_name')
      v_body = matches.get('var_body')

      if not v_name or not v_body:
        raise buff.get_error(IncompleteDirectiveError, 'bad variable definition')

      DEBUG(msg_prefix + 'variable defined: name=%s, value=%s', v_name, v_body)

      defs[re.compile(r'\${}'.format(v_name))] = v_body.strip()

      continue

    matches = RE_MACRO_DEF.match(line)
    if matches:
      matches = matches.groupdict()

      m_name = matches.get('macro_name')
      m_params = matches.get('macro_params')

      if not m_name:
        raise buff.get_error(IncompleteDirectiveError, 'bad macro definition')

      DEBUG(msg_prefix + 'macro defined: name=%s', m_name)

      if current_macro:
        raise buff.get_error(AssemblerError, 'overlapping macro definitions')

      current_macro = {
        'name':    m_name,
        'pattern': None,
        'params':  [p.strip() for p in m_params.strip().split(',')] if m_params else [],
        'body':    []
      }

      if current_macro['params'] and len(current_macro['params'][0]):
        arg_pattern = r'(?P<arg%i>(?:".*?")|(?:.*?))'
        arg_patterns = ',\s*'.join([arg_pattern % i for i in range(0, len(current_macro['params']))])

        current_macro['pattern'] = re.compile(r'^\s*\${}\s+{}\s*(?:[;/#].*)?$'.format(m_name, arg_patterns), re.MULTILINE)

      else:
        current_macro['pattern'] = re.compile(r'\s*\${}'.format(m_name))

      continue

    matches = RE_MACRO_END.match(line)
    if matches:
      if not current_macro:
        raise buff.get_error(AssemblerError, 'closing non-existing macro')

      macros[current_macro['pattern']] = current_macro
      DEBUG(msg_prefix + 'macro definition closed: name=%s', current_macro['name'])
      current_macro = None
      continue

    if current_macro:
      current_macro['body'].append(line)
      continue

    matches = RE_SECTION.match(line)
    if matches:
      matches = matches.groupdict()

      if 'name' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.section directive without section name')

      s_name = matches['name']

      if s_name not in sections_pass1:
        section_flags = SectionFlags.from_string(matches.get('flags') or '')
        section_type = SectionTypes.TEXT if section_flags.executable is True else SectionTypes.DATA

        section = sections_pass1[s_name] = Section(s_name, section_type, section_flags)
        DEBUG(msg_prefix + 'section %s created', s_name)

      curr_section = sections_pass1[s_name]

      if curr_section.type == SectionTypes.TEXT:
        text_section = curr_section
        DEBUG(msg_prefix + 'text section changed to %s', s_name)
      else:
        data_section = curr_section
        DEBUG(msg_prefix + 'data section changed to %s', s_name)

      continue

    matches = RE_DATA.match(line)
    if matches:
      matches = matches.groupdict()

      curr_section = data_section = sections_pass1[matches['name'] if 'name' in matches and matches['name'] else '.data']
      DEBUG(msg_prefix + 'data section is %s', data_section.name)
      continue

    matches = RE_TEXT.match(line)
    if matches:
      matches = matches.groupdict()

      curr_section = text_section = sections_pass1[matches['name'] if 'name' in matches and matches['name'] else '.text']
      DEBUG(msg_prefix + 'text section is %s', text_section.name)
      continue

    matches = RE_TYPE.match(line)
    if matches:
      matches = matches.groupdict()

      if 'type' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.type directive without a type')

      if 'name' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.type directive without a name')

      __handle_symbol_variable(matches['name'], matches['type'])

      continue

    matches = RE_BYTE.match(line)
    if matches:
      var = ByteSlot()
      __parse_integer(var, matches, 0xFF)
      __set_var_label(var)

      var.close()

      DEBUG(msg_prefix + 'record byte value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_SHORT.match(line)
    if matches:
      var = ShortSlot()
      __parse_integer(var, matches, 0xFFFF)
      __set_var_label(var)

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record byte value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_INT.match(line)
    if matches:
      var = IntSlot()
      __parse_integer(var, matches, 0xFFFFFFFF)
      __set_var_label(var)

      var.close()

      DEBUG(msg_prefix + 'record int value: name=%s, value=%s, refers_to=%s', var.name, var.value, var.refers_to)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_ASCII.match(line)
    if matches:
      var = AsciiSlot()
      __parse_string(var, matches)
      __set_var_label(var)

      var.close()

      DEBUG(msg_prefix + 'record ascii value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_STRING.match(line)
    if matches:
      var = StringSlot()
      __parse_string(var, matches)
      __set_var_label(var)

      var.close()

      DEBUG(msg_prefix + 'record string value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_SPACE.match(line)
    if matches:
      var = SpaceSlot()
      __parse_space(var, matches)
      __set_var_label(var)

      var.close()

      DEBUG(msg_prefix + 'record space: name=%s, value=%s', var.name, var.size)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_ALIGN.match(line)
    if matches:
      matches = matches.groupdict()

      if 'boundary' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.align directive without boundary')

      var = AlignSlot(int(matches['boundary']))

      DEBUG(msg_prefix + 'align: boundary=%s', var.boundary)
      data_section.content.append(var)
      continue

    matches = RE_GLOBAL.match(line)
    if matches:
      matches = matches.groupdict()

      if 'name' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.global directive without variable')

      name = matches['name']

      global_symbols.append(name)
      continue

    matches = RE_SET.match(line)
    if matches:
      matches = matches.groupdict()

      if 'name' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.set directive without variable')

      name = matches['name']

      if matches.get('current'):
        value = (curr_section.name, curr_section.ptr)

      elif matches.get('value_dec'):
        value = int(matches['value_dec'])

      elif matches.get('value_hex'):
        value = int(matches['value_hex'], base = 16)

      elif matches.get('value_label'):
        value = matches['value_label']

      else:
        raise buff.get_error(IncompleteDirectiveError, '.set directive with unknown value')

      DEBUG(msg_prefix + 'set variable: name=%s, value=%s', name, value)
      variables[name] = value

      continue

    matches = RE_LABEL.match(line)
    if matches:
      DEBUG('matches: %s', matches.groupdict())

      loc = buff.location.copy()
      loc.column = matches.start(2)

      label = Label(matches.groupdict()['label'], curr_section, loc)
      labels.append(label)

      DEBUG(msg_prefix + 'record label: name=%s', label.name)
      continue

    DEBUG(msg_prefix + 'line: %s', line)

    # label, instruction, 2nd pass flags
    emited_inst = None

    # Find instruction descriptor
    DEBUG(msg_prefix + 'instr set: %s', instruction_set)

    for desc in instruction_set.instructions:
      if not desc.pattern.match(line):
        continue
      break

    else:
      raise buff.get_error(UnknownPatternError, line, column = 0)

    emited_inst = desc.emit_instruction(logger, buff, line)
    emited_inst.desc = desc

    if labels:
      text_section.content.append((labels, emited_inst))

    else:
      text_section.content.append((None, emited_inst))

    labels = []

    emited_inst_disassemble = emited_inst.desc.instruction_set.disassemble_instruction(logger, emited_inst)
    DEBUG(msg_prefix + 'emitted instruction: %s (%s)', emited_inst_disassemble, UINT32_FMT(encoding_to_u32(emited_inst)))

    if verify_disassemble and line != emited_inst_disassemble:
      raise buff.get_error(DisassembleMismatchError, 'input="%s", emitted="%s"' % (line, emited_inst_disassemble))

    if isinstance(desc, cpu.instructions.SIS):
      DEBUG(msg_prefix + 'switching istruction set: inst_set=%s', emited_inst.immediate)

      instruction_set = cpu.instructions.get_instruction_set(emited_inst.immediate)

  for s_name, section in iteritems(sections_pass1):
    DEBUG('pass #1: section %s', s_name)

    if section.type == SectionTypes.TEXT:
      for labeled, inst in section.content:
        DEBUG('pass #1: inst=%s, labeled=%s', inst, labeled)

    else:
      for var in section.content:
        DEBUG('pass #1: %s', var)

  DEBUG('Pass #2')

  sections_pass2 = collections.OrderedDict()
  references = {}
  base_ptr = base_address

  for s_name, p1_section in iteritems(sections_pass1):
    section = sections_pass2[s_name] = Section(s_name, p1_section.type, p1_section.flags)

  symtab = sections_pass2['.symtab']
  reloctab = sections_pass2['.reloc']

  for s_name, section in iteritems(sections_pass2):
    p1_section = sections_pass1[s_name]

    section.base = base_ptr
    section.ptr  = base_ptr

    DEBUG('pass #2: section %s - base=%s', section.name, UINT32_FMT(section.base))

    if section.type == SectionTypes.SYMBOLS or section.type == SectionTypes.RELOC:
      continue

    if section.type == SectionTypes.DATA:
      for var in p1_section.content:
        ptr_prefix = 'pass #2: ' + UINT32_FMT(section.ptr) + ': '

        DEBUG(ptr_prefix + str(var))

        if isinstance(var, AlignSlot):
          aligned_ptr = align(var.boundary, section.ptr)
          padding_bytes = aligned_ptr - section.ptr

          if padding_bytes == 0:
            DEBUG(ptr_prefix + '  align %s to multiple of %s: aligned already, ignore', UINT32_FMT(section.ptr), var.boundary)
            continue

          padding = SpaceSlot()
          padding.size = padding_bytes

          DEBUG(ptr_prefix + '  align %s to multiple of %s: %s padding bytes => %s', UINT32_FMT(section.ptr), var.boundary, padding.size, UINT32_FMT(section.ptr + padding.size))
          DEBUG(ptr_prefix + '  %s', padding)

          section.content.append(padding)
          section.ptr += padding.size
          DEBUG(ptr_prefix + '  padding stored')

          continue

        if var.name:
          var.section = section
          var.section_ptr = section.ptr
          references['&' + var.name.name] = var

          symtab.content.append(var)

        if var.refers_to is not None:
          reference = var.refers_to

          DEBUG(ptr_prefix + '  refers to: %s', reference)

          if reference.label is not None:
            reloc = RelocSlot(reference.label[1:], patch_section = section, patch_address = section.ptr, patch_offset = 0, patch_size = 16, patch_add = reference.add)
            DEBUG(ptr_prefix + '  reloc slot created: %s', reloc)

          else:
            raise Exception()

          reloctab.content.append(reloc)
          var.refers_to = None

        if isinstance(var, IntSlot):
          if var.value is not None:
            section.content += var.value
            DEBUG(ptr_prefix + '  value stored')

          else:
            section.content.append(var)
            DEBUG(ptr_prefix + '  value missing - reserve space, fix in next pass')

          if var.size != 4:
            raise Exception()
          section.ptr += var.size

        elif isinstance(var, ShortSlot):
          if var.value is not None:
            section.content += var.value
            DEBUG(ptr_prefix + '  value stored')

          else:
            section.content.append(var)
            DEBUG(ptr_prefix + '  value missing - reserve space, fix in next pass')

          section.ptr += var.size

        elif isinstance(var, ByteSlot):
          if var.value is not None:
            section.content += var.value
            DEBUG(ptr_prefix + '  value stored')

          else:
            section.content.append(var)
            DEBUG(ptr_prefix + '  value missing - reserve space, fix in next pass')
          section.ptr += var.size

        elif type(var) == AsciiSlot or type(var) == StringSlot or isinstance(var, BytesSlot):
          section.content += var.value
          section.ptr += var.size
          DEBUG(ptr_prefix + '  value stored')

        elif type(var) == SpaceSlot:
          section.content.append(var)
          section.ptr += var.size
          DEBUG(ptr_prefix + '  value stored')

    if section.type == SectionTypes.TEXT:
      for labeled, inst in p1_section.content:
        ptr_prefix = 'pass #2: ' + UINT32_FMT(section.ptr) + ': '

        DEBUG(ptr_prefix + '%s (%s)', inst.desc.instruction_set.disassemble_instruction(logger, inst), UINT32_FMT(encoding_to_u32(inst)))

        inst.address = section.ptr

        if labeled:
          for label in labeled:
            var = FunctionSlot()
            var.name = label
            var.section = section
            var.section_ptr = section.ptr

            __set_var_location(var, location = label.location)

            var.close()

            symtab.content.append(var)

            references['&' + label.name] = var
            DEBUG(ptr_prefix + 'label entry "%s" created', label)

        if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to is not None:
          DEBUG(ptr_prefix + 'refers to: label=%s, relative=%s, inst_aligned=%s', inst.refers_to, inst.desc.relative_address, inst.desc.inst_aligned)
          DEBUG(ptr_prefix + 'refers to: %s', inst.refers_to)

          reloc = RelocSlot(inst.refers_to.label[1:], flags = RelocFlags.create(relative = inst.desc.relative_address, inst_aligned = inst.desc.inst_aligned), patch_section = section, patch_address = section.ptr)
          inst.fill_reloc_slot(logger, inst, reloc)
          sections_pass2['.reloc'].content.append(reloc)

          if inst.refers_to in references:
            reloc.patch_section = references[inst.refers_to].section

          DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)
          inst.refers_to = None

        section.content.append(inst)
        section.ptr += 4

    base_ptr = align_to_next_mmap(section.ptr) if mmapable_sections else align_to_next_page(section.ptr)

  DEBUG('Pass #3')

  sections_pass3 = {}

  for s_name, p2_section in iteritems(sections_pass2):
    section = Section(s_name, p2_section.type, p2_section.flags)
    sections_pass3[s_name] = section
    section.base = p2_section.base
    section.ptr  = section.base

  symtab = sections_pass3['.symtab']
  reloctab = sections_pass3['.reloc']

  for s_name, section in iteritems(sections_pass3):
    DEBUG('pass #3: section %s', section.name)

    p2_section = sections_pass2[s_name]

    if section.type == SectionTypes.SYMBOLS:
      symtab = section

    elif section.type == SectionTypes.RELOC:
      reloctab = section

    for item in p2_section.content:
      ptr_prefix = 'pass #3: ' + UINT32_FMT(section.ptr) + ': '

      if section.type == SectionTypes.SYMBOLS:
        if (type(item.name) is Label and item.name.name in global_symbols) or item.name in global_symbols:
          item.flags.globally_visible = True

      elif type(item) == IntSlot:
        if item.refers_to:
          reference, item.refers_to = item.refers_to, None

          DEBUG(ptr_prefix + 'refers to: %s', reference)

          reloc = RelocSlot(reference.label[1:], patch_section = references[item.refers_to].section, patch_address = section.ptr, patch_offset = 0, patch_size = 16, patch_add = reference.add)
          DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)

          reloctab.content.append(reloc)

          item.value = 0x79797979

        item.close()
        item = item.value

      elif hasattr(item, 'refers_to') and item.refers_to:
        reference, item.refers_to = item.refers_to, None

        DEBUG(ptr_prefix + 'refers to: label=%s, relative=%s, inst_aligned=%s', reference, item.desc.relative_address, item.desc.inst_aligned)

        reloc = RelocSlot(reference.label[1:], flags = RelocFlags.create(relative = item.desc.relative_address, inst_aligned = item.desc.inst_aligned), patch_section = section, patch_address = section.ptr, patch_add = reference.add)
        item.fill_reloc_slot(logger, item, reloc)
        DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)
        reloctab.content.append(reloc)

      DEBUG(ptr_prefix + str(item))

      if not isinstance(item, list):
        item = [item]

      for i in item:
        section.content.append(i)
        section.ptr += sizeof(i)

    DEBUG('pass #3: section %s finished: %s', section.name, section)

  DEBUG('Bytecode sections:')
  for s_name, section in iteritems(sections_pass3):
    DEBUG(str(section))

  DEBUG('Bytecode translation completed')

  return sections_pass3
