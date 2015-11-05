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

from ..mm import UInt8, UInt16, ADDR_FMT, PAGE_SIZE
from ..mm.binary import SectionTypes, SectionFlags, SymbolFlags, RelocFlags
from ..util import align, str2bytes

align_to_next_page = functools.partial(align, PAGE_SIZE)
align_to_next_mmap = functools.partial(align, mmap.PAGESIZE)

RE_COMMENT = re.compile(r'^\s*[/;].*?$', re.MULTILINE)
RE_INCLUDE = re.compile(r'^\s*\.include\s+"(?P<file>[a-zA-Z0-9_\-/\.]+)\s*"$', re.MULTILINE)
RE_IFDEF = re.compile(r'^\s*\.ifdef\s+(?P<var>[a-zA-Z0-9_]+)\s*$', re.MULTILINE)
RE_IFNDEF = re.compile(r'^\s*\.ifndef\s+(?P<var>[a-zA-Z0-9_]+)\s*$', re.MULTILINE)
RE_ELSE = re.compile(r'^\s*\.else\s*$', re.MULTILINE)
RE_ENDIF = re.compile(r'^\s*\.endif\s*$', re.MULTILINE)
RE_VAR_DEF = re.compile(r'^\s*\.def\s+(?P<var_name>[a-zA-Z][a-zA-Z0-9_]*):\s*(?P<var_body>.*?)$', re.MULTILINE)
RE_MACRO_DEF = re.compile(r'^\s*\.macro\s+(?P<macro_name>[a-zA-Z][a-zA-Z0-9_]*)(?:\s+(?P<macro_params>.*?))?:$', re.MULTILINE | re.DOTALL)
RE_MACRO_END = re.compile(r'^\s*\.end\s*$', re.MULTILINE)
RE_ASCII = re.compile(r'^\s*\.ascii\s+"(?P<value>.*?)"\s*$', re.MULTILINE)
RE_BYTE = re.compile(r'^\s*\.byte\s+(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>(?:0)|(?:-?[1-9][0-9]*))|(?P<value_var>[a-zA-Z][a-zA-Z0-9_]*))\s*$', re.MULTILINE)
RE_DATA = re.compile(r'^\s*\.data(?:\s+(?P<name>\.[a-z][a-z0-9_]*))?\s*$', re.MULTILINE)
RE_INT = re.compile(r'^\s*\.int\s+(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_var>[a-zA-Z][a-zA-Z0-9_]*)|(?P<value_label>&[a-zA-Z_\.][a-zA-Z0-9_]*))\s*$', re.MULTILINE)
RE_SECTION = re.compile(r'^\s*\.section\s+(?P<name>\.[a-zA-z0-9_]+)(?:,\s*(?P<flags>[rwxlbmg]*))?\s*$', re.MULTILINE)
RE_SET = re.compile(r'^\s*\.set\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?:(?P<current>\.)|(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_label>&[a-zA-Z][a-zA-Z0-9_]*))\s*$', re.MULTILINE)
RE_SIZE = re.compile(r'^\s*\.size\s+(?P<size>[1-9][0-9]*)\s*$', re.MULTILINE)
RE_SPACE = re.compile(r'^\s*\.space\s+(?P<size>[1-9][0-9]*)\s*$', re.MULTILINE)
RE_STRING = re.compile(r'^\s*\.string\s+"(?P<value>.*?)"\s*$', re.MULTILINE)
RE_TEXT = re.compile(r'^\s*\.text(?:\s+(?P<name>\.[a-z][a-z0-9_]*))?\s*$', re.MULTILINE)
RE_TYPE = re.compile(r'^\s*\.type\s+(?P<name>[a-zA-Z_\.][a-zA-Z0-9_]*),\s*(?P<type>(?:char|byte|int|ascii|string|space))\s*$', re.MULTILINE)
RE_GLOBAL = re.compile(r'^\s*.global\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*$', re.MULTILINE)

class AssemblerError(Exception):
  def __init__(self, filename, lineno, msg, line):
    super(AssemblerError, self).__init__('{}:{}: {}'.format(filename, lineno, msg))

    self.filename = filename
    self.lineno   = lineno
    self.msg      = msg
    self.line     = line

class IncompleteDirectiveError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(IncompleteDirectiveError, self).__init__(filename, lineno, 'Incomplete directive: %s' % msg, line)

class UnknownFileError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(UnknownFileError, self).__init__(filename, lineno, 'Unknown file: %s' % msg, line)

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

    self.filename = filename
    self.lineno = 0
    self.last_line = None

  def get_line(self):
    while self.buff:
      self.lineno += 1

      line = self.buff.pop(0)

      if isinstance(line, tuple):
        self.lineno = line[1]
        self.filename = line[0]

        self.DEBUG('buffer: file switch: filename=%s, lineno=%s', self.filename, self.lineno)
        continue

      if not line:
        continue

      self.DEBUG('buffer: new line %s:%s: %s', self.filename, self.lineno, line)
      self.last_line = line
      return line

    self.last_line = None
    return None

  def put_line(self, line):
    self.buff.insert(0, line)
    self.lineno -= 1

  def put_buffer(self, buff, filename = None):
    filename = filename or '<unknown>'

    self.buff.insert(0, (self.filename, self.lineno))

    if isinstance(buff, string_types):
      buff = buff.split('\n')

    for line in reversed(buff):
      self.buff.insert(0, line)

    self.buff.insert(0, (filename, 0))

  def has_lines(self):
    return len(self.buff) > 0

  def get_error(self, cls, msg):
    return cls(self.filename, self.lineno, msg, self.last_line)

class Section(object):
  def __init__(self, s_name, s_type, s_flags):
    super(Section, self).__init__()

    self.name    = s_name
    self.type    = s_type
    self.flags   = s_flags
    self.content = []

    self.base = None
    self.ptr  = UInt16(0)

  def __getattr__(self, name):
    if name == 'data_size':
      return sum([sizeof(i) for i in self.content])

    if name == 'file_size':
      return align_to_next_mmap(self.data_size) if self.flags.mmapable == 1 else self.data_size

    if name == 'items':
      return len(self.content)

  def __repr__(self):
    return '<Section: name={}, type={}, flags={}, base={}, ptr={}, items={}, data_size={}, file_size={}>'.format(self.name, self.type, self.flags.to_string(), self.base, self.ptr, self.items, self.data_size, self.file_size)

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
  def __init__(self, name, section, filename, lineno):
    super(Label, self).__init__()

    self.name = name
    self.section = section

    self.filename = filename
    self.lineno = lineno

  def __repr__(self):
    return '<label {} in section {} ({}:{})>'.format(self.name, self.section.name if self.section else None, self.filename, self.lineno)

class RelocSlot(object):
  def __init__(self, name, flags = None, patch_section = None, patch_address = None, patch_offset = None, patch_size = None):
    super(RelocSlot, self).__init__()

    self.name = name
    self.flags = flags or RelocFlags()
    self.patch_section = patch_section
    self.patch_address = patch_address
    self.patch_offset = patch_offset
    self.patch_size = patch_size

    self.size = UInt16(0)

  def __repr__(self):
    return '<RelocSlot: name=%s, flags=%s, section=%s, address=%s, offset=%s, size=%s>' % (self.name, self.flags.to_string(), self.patch_section, ADDR_FMT(self.patch_address), self.patch_offset, self.patch_size)

class DataSlot(object):
  def __init__(self):
    super(DataSlot, self).__init__()

    self.name  = None
    self.size  = None
    self.refers_to = None
    self.value = None

    self.flags = SymbolFlags()

    self.section = None
    self.section_ptr = None

    self.filename = None
    self.lineno = None

  def close(self):
    pass

class ByteSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR

  def close(self):
    self.size = UInt16(1)

    if self.refers_to:
      return

    self.value = UInt8(self.value or 0)

  def __repr__(self):
    return '<ByteSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class IntSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.INT

  def close(self):
    self.size = UInt16(2)

    if self.refers_to:
      return

    self.value = UInt16(self.value or 0)
    self.size = UInt16(2)

  def __repr__(self):
    return '<IntSlot: name={}, size={}, section={}, value={}, refers_to={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value, self.refers_to)

class CharSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR

  def close(self):
    self.value = UInt8(ord(self.value or '\0'))
    self.size = UInt16(1)

  def __repr__(self):
    return '<CharSlot: name={}, section={}, value={}>'.format(self.name, self.section.name if self.section else '', self.value)

class SpaceSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = None
    self.size = UInt16(self.size)

  def __repr__(self):
    return '<SpaceSlot: name={}, size={}, section={}>'.format(self.name, self.size, self.section.name if self.section else '')

class AsciiSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = self.value or ''
    self.value = [UInt8(ord(c)) for c in self.value]
    self.size = UInt16(len(self.value))

  def __repr__(self):
    return '<AsciiSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class StringSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.STRING

  def close(self):
    self.value = self.value or ''
    self.value = [UInt8(ord(c)) for c in self.value] + [UInt8(0)]
    self.size = UInt16(len(self.value))

  def __repr__(self):
    return '<StringSlot: name={}, size={}, section={}, value={}>'.format(self.name, self.size, self.section.name if self.section else '', self.value)

class FunctionSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION

  def close(self):
    self.size = UInt16(0)

  def __repr__(self):
    return '<FunctionSlot: name={}, section={}>'.format(self.name, self.section.name if self.section else '')

def sizeof(o):
  if isinstance(o, RelocSlot):
    return 0

  if isinstance(o, DataSlot):
    return o.size.u16

  if isinstance(o, ctypes.LittleEndianStructure):
    return ctypes.sizeof(o)

  return None

if PY2:
  def decode_string(s):
    return s.decode('string_escape')

else:
  def decode_string(s):
    return str2bytes(s).decode('unicode_escape')

def translate_buffer(logger, buff, base_address = None, mmapable_sections = False, writable_sections = False, filename = None, defines = None, includes = None):
  DEBUG = logger.debug

  filename = filename or '<unknown>'
  defines = defines or []
  includes = includes or []
  includes.insert(0, os.getcwd())

  buff = Buffer(logger, filename, buff.split('\n'))

  base_address = base_address or UInt16(0)

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
      section.flags.mmapable = 1

  if writable_sections:
    for section in [_section for _section in itervalues(sections_pass1) if _section.name in ('.text', '.rodata', '.data', '.bss')]:
      section.flags.writable = 1

  DEBUG('Pass #1')

  labeled = []

  line = None
  lineno = None

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

  def __get_refers_to_operand(inst):
    r_address = references[inst.refers_to].section_ptr.u16

    if inst.refers_to.startswith(''):
      r_address -= (inst.address.u16 + 4)

    return r_address

  def __parse_byte(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = buff.lineno

    matches = matches.groupdict()

    v_value = matches.get('value_dec')
    if v_value:
      var.value = int(v_value)
      return

    v_value = matches.get('value_hex')
    if v_value:
      var.value = int(v_value, base = 16)
      return

    v_value = matches.get('value_var')
    if v_value:
      referred_var = variables[matches['value_var']]

      if isinstance(referred_var, integer_types):
        var.value = referred_var
      else:
        var.refers_to = referred_var

      return

    raise buff.get_error(IncompleteDirectiveError, '.byte directive without a meaningful value')

  def __parse_int(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = buff.lineno

    matches = matches.groupdict()

    v_value = matches.get('value_dec')
    if v_value:
      var.value = int(v_value)
      return

    v_value = matches.get('value_hex')
    if v_value:
      var.value = int(v_value, base = 16)
      return

    v_value = matches.get('value_var')
    if v_value:
      if matches['value_var'] not in variables:
        raise buff.get_error(IncompleteDirectiveError, 'unknown variable named "%s"' % matches['value_var'])

      referred_var = variables[matches['value_var']]

      if isinstance(referred_var, integer_types):
        var.value = referred_var
      else:
        var.refers_to = referred_var

      return

    v_value = matches.get('value_label')
    if v_value:
      var.refers_to = v_value
      return

    raise buff.get_error(IncompleteDirectiveError, '.byte directive without a meaningful value')

  def __parse_ascii(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = lineno

    matches = matches.groupdict()

    v_value = matches.get('value')
    if not v_value:
      raise buff.get_error(IncompleteDirectiveError, '.ascii directive without a string')

    DEBUG('Pre-decode: (%s) %s', type(v_value), ', '.join([str(ord(c)) for c in v_value]))
    s = decode_string(v_value)
    DEBUG('Pre-decode: (%s) %s', type(s), ', '.join([str(ord(c)) for c in s]))

    var.value = decode_string(v_value)

  def __parse_string(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = lineno

    matches = matches.groupdict()

    v_value = matches.get('value')
    if not v_value:
      raise buff.get_error(IncompleteDirectiveError, '.string directive without a string')

    DEBUG('Pre-decode: (%s) %s', type(v_value), ', '.join([str(ord(c)) for c in v_value]))
    s = decode_string(v_value)
    DEBUG('Pre-decode: (%s) %s', type(s), ', '.join([str(ord(c)) for c in s]))

    var.value = decode_string(v_value)

  def __parse_space(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = lineno

    matches = matches.groupdict()

    if 'size' not in matches:
      raise buff.get_error(IncompleteDirectiveError, '.size directive without a size')

    var.size = int(matches['size'])

  def __handle_symbol_variable(v_name, v_type):
    if v_type == 'char':
      var = CharSlot()

    elif v_type == 'byte':
      var = ByteSlot()

    elif v_type == 'int':
      var = IntSlot()

    elif v_type == 'ascii':
      var = AsciiSlot()

    elif v_type == 'string':
      var = StringSlot()

    elif v_type == 'space':
      var = SpaceSlot()

    var.name = Label(v_name, curr_section, buff.filename, buff.lineno)
    var.filename = buff.filename
    var.lineno = buff.lineno

    while buff.has_lines():
      line = buff.get_line()

      if line is None:
        var.close()
        data_section.content.append(var)
        return

      matches = RE_COMMENT.match(line)
      if matches:
        continue

      msg_prefix = 'pass #1: {}:{}: '.format(os.path.split(buff.filename)[1], buff.lineno)

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

        var.size = UInt16(int(matches['size']))
        continue

      matches = RE_INT.match(line)
      if matches:
        __parse_int(var, matches)
        continue

      matches = RE_ASCII.match(line)
      if matches:
        __parse_ascii(var, matches)
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
        __parse_byte(var, matches)
        continue

      buff.put_line(line)
      break

    var.close()
    data_section.content.append(var)

  labels = []
  variables = {}

  instruction_set = cpu.instructions.DuckyInstructionSet

  defs = collections.OrderedDict()

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

    msg_prefix = 'pass #1: {}:{}: '.format(os.path.split(buff.filename)[1], buff.lineno)

    line = __apply_defs(line)

    if not current_macro and __apply_macros(line):
      DEBUG(msg_prefix + 'macro replaced, get fresh line')
      continue

    matches = RE_COMMENT.match(line)
    if matches:
      continue

    msg_prefix = 'pass #1: {}:{}: '.format(os.path.split(buff.filename)[1], buff.lineno)

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
      matches = matches.groupdict()

      if 'file' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.include directive without path')

      DEBUG(msg_prefix + 'include: file=%s', matches['file'])

      replace = None

      for d in includes:
        filename = os.path.join(d, matches['file'])
        DEBUG(msg_prefix + '  checking file %s', filename)

        try:
          with open(filename, 'r') as f_in:
            replace = f_in.read()

        except IOError:
          DEBUG('    failed to read')

        else:
          DEBUG('    read as replacement')
          break

      if replace is None:
        raise buff.get_error(UnknownFileError, matches['file'])

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
        section_type = SectionTypes.TEXT if section_flags.executable == 1 else SectionTypes.DATA

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
      __parse_byte(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: {}'.format(labels))

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record byte value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_INT.match(line)
    if matches:
      var = IntSlot()
      __parse_int(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: {}'.format(labels))

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record int value: name=%s, value=%s, refers_to=%s', var.name, var.value, var.refers_to)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_ASCII.match(line)
    if matches:
      var = AsciiSlot()
      __parse_ascii(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: {}'.format(labels))

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record ascii value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_STRING.match(line)
    if matches:
      var = StringSlot()
      __parse_string(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: {}'.format(labels))

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record string value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_SPACE.match(line)
    if matches:
      var = SpaceSlot()
      __parse_space(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: {}'.format(labels))

      var.name = labels[0] if labels else None
      var.close()

      DEBUG(msg_prefix + 'record space: name=%s, value=%s', var.name, var.size)
      data_section.content.append(var)

      labels = []
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
        value = (curr_section.name, UInt16(curr_section.ptr.u16))

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

    if line.endswith(':'):
      label = Label(line.strip()[:-1], curr_section, buff.filename, buff.lineno)
      labels.append(label)

      DEBUG(msg_prefix + 'record label: name=%s', label.name)
      continue

    DEBUG(msg_prefix + 'line: %s', line)

    # label, instruction, 2nd pass flags
    emited_inst = None

    # Find instruction descriptor
    line = line.strip()

    for desc in instruction_set.instructions:
      DEBUG(msg_prefix + 'pattern: %s', desc.pattern.pattern)
      if not desc.pattern.match(line):
        continue
      break

    else:
      raise buff.get_error(AssemblerError, 'Unknown pattern: line="{}"'.format(line))

    emited_inst = desc.emit_instruction(logger, line)
    emited_inst.desc = desc

    if labels:
      text_section.content.append((labels, emited_inst))

    else:
      text_section.content.append((None, emited_inst))

    labels = []

    DEBUG(msg_prefix + 'emitted instruction: %s', emited_inst.desc.instruction_set.disassemble_instruction(emited_inst))

    if isinstance(desc, cpu.instructions.Inst_SIS):
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
  base_ptr = UInt16(base_address.u16)

  for s_name, p1_section in iteritems(sections_pass1):
    section = sections_pass2[s_name] = Section(s_name, p1_section.type, p1_section.flags)

  symtab = sections_pass2['.symtab']
  reloctab = sections_pass2['.reloc']

  for s_name, section in iteritems(sections_pass2):
    p1_section = sections_pass1[s_name]

    section.base = UInt16(base_ptr.u16)
    section.ptr  = UInt16(base_ptr.u16)

    DEBUG('pass #2: section %s - base=%s', section.name, ADDR_FMT(section.base.u16))

    if section.type == SectionTypes.SYMBOLS or section.type == SectionTypes.RELOC:
      continue

    if section.type == SectionTypes.DATA:
      for var in p1_section.content:
        ptr_prefix = 'pass #2: ' + ADDR_FMT(section.ptr.u16) + ': '

        DEBUG(ptr_prefix + str(var))

        if var.name:
          var.section = section
          var.section_ptr = UInt16(section.ptr.u16)
          references['&' + var.name.name] = var

          symtab.content.append(var)

        if var.refers_to:
          refers_to = var.refers_to

          if isinstance(refers_to, tuple):
            reloc = RelocSlot(refers_to[0], patch_section = section, patch_address = section.ptr.u16, patch_offset = 0, patch_size = 16)
            DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)

          else:
            reloc = RelocSlot(refers_to[1:], patch_section = section, patch_address = section.ptr.u16, patch_offset = 0, patch_size = 16)
            DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)

          reloctab.content.append(reloc)
          var.refers_to = None

        if type(var) == IntSlot:
          if var.value:
            section.content.append(UInt8(var.value.u16 & 0x00FF))
            section.content.append(UInt8((var.value.u16 & 0xFF00) >> 8))
            DEBUG(ptr_prefix + 'value stored')

          else:
            section.content.append(var)
            DEBUG(ptr_prefix + 'value missing - reserve space, fix in next pass')

          section.ptr.u16 += 2

        elif type(var) == ByteSlot:
          section.content.append(UInt8(var.value.u8))
          section.ptr.u16 += var.size.u16
          DEBUG(ptr_prefix + 'value stored')

        elif type(var) == AsciiSlot or type(var) == StringSlot:
          for i in range(0, var.size.u16):
            section.content.append(var.value[i])
            section.ptr.u16 += 1

          if var.size.u16 % 2 != 0:
            section.content.append(UInt8(0))
            section.ptr.u16 += 1

          DEBUG(ptr_prefix + 'value stored')

        elif type(var) == SpaceSlot:
          section.content.append(var)
          section.ptr.u16 += var.size.u16
          DEBUG(ptr_prefix + 'value stored')

    if section.type == SectionTypes.TEXT:
      for labeled, inst in p1_section.content:
        ptr_prefix = 'pass #2: ' + ADDR_FMT(section.ptr.u16) + ': '

        inst.address = UInt16(section.ptr.u16)

        if labeled:
          for label in labeled:
            var = FunctionSlot()
            var.name = label
            var.section = section
            var.section_ptr = UInt16(section.ptr.u16)

            var.filename = label.filename
            var.lineno = label.lineno

            var.close()

            symtab.content.append(var)

            references['&' + label.name] = var
            DEBUG(ptr_prefix + 'label entry "%s" created', label)

        if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to:
          reloc = RelocSlot(inst.refers_to[1:], flags = RelocFlags(relative = inst.desc.relative_address), patch_section = section, patch_address = section.ptr.u16)
          inst.desc.fill_reloc_slot(logger, inst, reloc)
          sections_pass2['.reloc'].content.append(reloc)

          if inst.refers_to in references:
            reloc.patch_section = references[inst.refers_to].section

          DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)
          inst.refers_to = None

        section.content.append(inst)
        DEBUG(ptr_prefix + inst.desc.instruction_set.disassemble_instruction(inst))
        section.ptr.u16 += 4

    base_ptr.u16 = align_to_next_mmap(section.ptr.u16) if mmapable_sections else align_to_next_page(section.ptr.u16)

  DEBUG('Pass #3')

  sections_pass3 = {}

  for s_name, p2_section in iteritems(sections_pass2):
    section = Section(s_name, p2_section.type, p2_section.flags)
    sections_pass3[s_name] = section
    section.base = UInt16(p2_section.base.u16)
    section.ptr  = UInt16(section.base.u16)

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
      ptr_prefix = 'pass #3: ' + ADDR_FMT(section.ptr.u16) + ': '

      if section.type == SectionTypes.SYMBOLS:
        if (type(item.name) is Label and item.name.name in global_symbols) or item.name in global_symbols:
          item.flags.globally_visible = 1

      elif type(item) == IntSlot:
        if item.refers_to:
          refers_to = item.refers_to

          if isinstance(refers_to, tuple):
            referred_section = sections_pass2[item.refers_to[0]]

            reloc = RelocSlot(refers_to[0], patch_section = referred_section, patch_address = section.ptr.u16, patch_offset = 0, patch_size = 16)
            DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)

          else:
            reloc = RelocSlot(refers_to[1:], patch_section = references[item.refers_to].section, patch_address = section.ptr.u16, patch_offset = 0, patch_size = 16)
            DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)

          reloctab.content.append(reloc)

          item.value = 0x7979
          item.refers_to = None

        item.close()

        item = [UInt8(item.value.u16 & 0x00FF), UInt8((item.value.u16 & 0xFF00) >> 8)]

      elif hasattr(item, 'refers_to') and item.refers_to:
        DEBUG(ptr_prefix + 'fix reference: %s', item)

        reloc = RelocSlot(item.refers_to[1:], flags = RelocFlags(relative = item.desc.relative_address), patch_section = section, patch_address = section.ptr.u16)
        item.desc.fill_reloc_slot(logger, item, reloc)
        DEBUG(ptr_prefix + 'reloc slot created: %s', reloc)
        reloctab.content.append(reloc)

      DEBUG(ptr_prefix + str(item))

      if not isinstance(item, list):
        item = [item]

      for i in item:
        section.content.append(i)
        section.ptr.u16 += sizeof(i)

    DEBUG('pass #3: section %s finished: %s', section.name, section)

  DEBUG('Bytecode sections:')
  for s_name, section in iteritems(sections_pass3):
    DEBUG(str(section))

  DEBUG('Bytecode translation completed')

  return sections_pass3
