#!/usr/bin/python

import collections
import ctypes
import functools
import mmap
import os.path
import re
import types

from .. import cpu
from .. import mm
from ..cpu.coprocessor.math_copro import MathCoprocessorInstructionSet  # noqa - it's not unused, SIS instruction may need it but that's hidden from flake

from ..mm import UInt8, UInt16, ADDR_FMT, PAGE_SIZE
from ..mm.binary import SectionTypes
from ..util import debug, align

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
RE_SECTION = re.compile(r'^\s*\.section\s+(?P<name>\.[a-zA-z0-9_]+)(?:,\s*(?P<flags>[rwxb]*))?\s*$', re.MULTILINE)
RE_SET = re.compile(r'^\s*\.set\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?:(?P<current>\.)|(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_label>&[a-zA-Z][a-zA-Z0-9_]*))\s*$', re.MULTILINE)
RE_SIZE = re.compile(r'^\s*\.size\s+(?P<size>[1-9][0-9]*)\s*$', re.MULTILINE)
RE_SPACE = re.compile(r'^\s*\.space\s+(?P<size>[1-9][0-9]*)\s*$', re.MULTILINE)
RE_STRING = re.compile(r'^\s*\.string\s+"(?P<value>.*?)"\s*$', re.MULTILINE)
RE_TEXT = re.compile(r'^\s*\.text(?:\s+(?P<name>\.[a-z][a-z0-9_]*))?\s*$', re.MULTILINE)
RE_TYPE = re.compile(r'^\s*\.type\s+(?P<name>[a-zA-Z_\.][a-zA-Z0-9_]*),\s*(?P<type>(?:char|byte|int|ascii|string|space))\s*$', re.MULTILINE)

class AssemblerError(Exception):
  def __init__(self, filename, lineno, msg, line):
    super(AssemblerError, self).__init__('%s:%s: %s' % (filename, lineno, msg))

    self.filename = filename
    self.lineno   = lineno
    self.msg      = msg
    self.line     = line

class IncompleteDirectiveError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(IncompleteDirectiveError, self).__init__(filename, lineno, 'Incomplete directive: %s' % msg, line)

class Buffer(object):
  def __init__(self, filename, buff):
    super(Buffer, self).__init__()

    self.buff = buff

    self.filename = filename
    self.lineno = 0
    self.last_line = None

  def get_line(self):
    while len(self.buff):
      self.lineno += 1

      line = self.buff.pop(0)

      if isinstance(line, types.TupleType):
        self.lineno = line[1]
        self.filename = line[0]

        debug('buffer: file switch: filename=%s, lineno=%s', self.filename, self.lineno)
        continue

      if not line:
        continue

      debug('buffer: new line %s:%s: %s', self.filename, self.lineno, line)
      self.last_line = line
      return line

    else:
      self.last_line = None
      return None

  def put_line(self, line):
    self.buff.insert(0, line)
    self.lineno -= 1

  def put_buffer(self, buff, filename = None):
    filename = filename or '<unknown>'

    self.buff.insert(0, (self.filename, self.lineno))

    if isinstance(buff, types.StringType):
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

    self.base = UInt16(0)
    self.ptr  = UInt16(0)

  def __getattr__(self, name):
    if name == 'size':
      return sum([sizeof(i) for i in self.content])

    if name == 'items':
      return len(self.content)

    if name == 'is_bss':
      return 'b' in self.flags

  def __repr__(self):
    return '<Section: name=%s, type=%s, flags=%s, base=%s, ptr=%s, items=%s, size=%s>' % (self.name, self.type, self.flags, self.base, self.ptr, self.items, self.size)

class TextSection(Section):
  def __init__(self, s_name, flags = None):
    super(TextSection, self).__init__(s_name, SectionTypes.TEXT, flags or 'rwx')

class RODataSection(Section):
  def __init__(self, s_name, flags = None):
    super(RODataSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rw')

class DataSection(Section):
  def __init__(self, s_name, flags = None):
    super(DataSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rw')

class BssSection(Section):
  def __init__(self, s_name, flags = None):
    super(BssSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rwb')

class Label(object):
  def __init__(self, name, section, filename, lineno):
    super(Label, self).__init__()

    self.name = name
    self.section = section

    self.filename = filename
    self.lineno = lineno

  def __repr__(self):
    return '<label %s in section %s (%s:%s)>' % (self.name, self.section.name, self.filename, self.lineno)

class DataSlot(object):
  def __init__(self):
    super(DataSlot, self).__init__()

    self.name  = None
    self.size  = None
    self.refers_to = None
    self.value = None

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
    return '<ByteSlot: name=%s, size=%s, section=%s, value=%s>' % (self.name, self.size, self.section.name if self.section else '', self.value)

class IntSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.INT

  def close(self):
    self.size = UInt16(2)

    if self.refers_to:
      return

    self.value = UInt16(self.value or 0)
    self.size = UInt16(2)

  def __repr__(self):
    return '<IntSlot: name=%s, size=%s, section=%s, value=%s, refers_to=%s>' % (self.name, self.size, self.section.name if self.section else '', self.value, self.refers_to)

class CharSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.CHAR

  def close(self):
    self.value = UInt8(ord(self.value or '\0'))
    self.size = UInt16(1)

  def __repr__(self):
    return '<CharSlot: name=%s, section=%s, value=%s>' % (self.name, self.section.name if self.section else '', self.value)

class SpaceSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = None
    self.size = UInt16(self.size)

  def __repr__(self):
    return '<SpaceSlot: name=%s, size=%s, section=%s>' % (self.name, self.size, self.section.name if self.section else '')

class AsciiSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.ASCII

  def close(self):
    self.value = self.value or ''
    self.value = [UInt8(ord(c)) for c in self.value]
    self.size = UInt16(len(self.value))

  def __repr__(self):
    return '<AsciiSlot: name=%s, size=%s, section=%s, value=%s>' % (self.name, self.size, self.section.name if self.section else '', self.value)

class StringSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.STRING

  def close(self):
    self.value = self.value or ''
    self.value = [UInt8(ord(c)) for c in self.value] + [UInt8(0)]
    self.size = UInt16(len(self.value))

  def __repr__(self):
    return '<StringSlot: name=%s, size=%s, section=%s, value=%s>' % (self.name, self.size, self.section.name if self.section else '', self.value)

class FunctionSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION

  def close(self):
    self.size = UInt16(0)

  def __repr__(self):
    return '<FunctionSlot: name=%s, section=%s>' % (self.name, self.section.name if self.section else '')

def sizeof(o):
  if isinstance(o, DataSlot):
    return o.size.u16

  if isinstance(o, ctypes.LittleEndianStructure):
    return ctypes.sizeof(o)

  return None

def translate_buffer(buff, base_address = None, mmapable_sections = False, filename = None, defines = None):
  filename = filename or '<unknown>'
  defines = defines or []

  buff = Buffer(filename, buff.split('\n'))

  base_address = base_address or UInt16(0)

  sections_pass1 = {
    '.text': TextSection('.text'),
    '.rodata': RODataSection('.rodata'),
    '.data': DataSection('.data'),
    '.bss':  BssSection('.bss'),
    '.symtab': Section('.symtab', SectionTypes.SYMBOLS, '')
  }

  debug('Pass #1')

  labeled = []

  line = None
  lineno = None

  def __apply_defs(line):
    orig_line = line

    for def_pattern, def_value in defs.iteritems():
      line = def_pattern.sub(def_value, line)

    if orig_line != line:
      debug(msg_prefix + 'variables replaced: line="%s"', line)

    return line

  def __apply_macros(line):
    for m_pattern, m_desc in macros.iteritems():
      matches = m_pattern.match(line)
      if not matches:
        continue

      debug(msg_prefix + 'replacing macro: name=%s', m_desc['name'])

      if len(m_desc['params']):
        matches = matches.groupdict()

        replace_map = {}
        for i in range(0, len(m_desc['params'])):
          replace_map[re.compile(r'#%s' % m_desc['params'][i])] = matches['arg%i' % i]

        debug(msg_prefix + 'macro args: %s', ', '.join(['%s => %s' % (pattern.pattern, repl) for pattern, repl in replace_map.iteritems()]))

        body = []
        for line in m_desc['body']:
          for pattern, repl in replace_map.iteritems():
            line = pattern.sub(repl, line)
          body.append(line)

        buff.put_buffer(body)

      else:
        buff.put_buffer(m_desc['body'])

      return True

    else:
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

    v_value = matches.get('value_dec', None)
    if v_value:
      var.value = int(v_value)
      return

    v_value = matches.get('value_hex', None)
    if v_value:
      var.value = int(v_value, base = 16)
      return

    v_value = matches.get('value_var', None)
    if v_value:
      referred_var = variables[matches['value_var']]

      if isinstance(referred_var, types.IntType):
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

    v_value = matches.get('value_dec', None)
    if v_value:
      var.value = int(v_value)
      return

    v_value = matches.get('value_hex', None)
    if v_value:
      var.value = int(v_value, base = 16)
      return

    v_value = matches.get('value_var', None)
    if v_value:
      referred_var = variables[matches['value_var']]

      if isinstance(referred_var, types.IntType):
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

    v_value = matches.get('value', None)
    if not v_value:
      raise buff.get_error(IncompleteDirectiveError, '.ascii directive without a string')

    var.value = v_value.decode('string_escape')

  def __parse_string(var, matches):
    if not var.lineno:
      var.filename = buff.filename
      var.lineno = lineno

    matches = matches.groupdict()

    v_value = matches.get('value', None)
    if not v_value:
      raise buff.get_error(IncompleteDirectiveError, '.string directive without a string')

    var.value = v_value.decode('string_escape')

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

      msg_prefix = 'pass #1: %s:%s: ' % (os.path.split(buff.filename)[1], buff.lineno)

      line = __apply_defs(line)

      if not current_macro and __apply_macros(line):
        debug(msg_prefix + 'macro replaced, get fresh line')
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

  debug('Pass #1: text section is .text')
  debug('Pass #1: data section is .data')

  text_section = sections_pass1['.text']
  data_section = sections_pass1['.data']
  curr_section = text_section

  ifs = []

  def __fast_forward():
    debug(msg_prefix + 'fast forwarding')

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

    msg_prefix = 'pass #1: %s:%s: ' % (os.path.split(buff.filename)[1], buff.lineno)

    line = __apply_defs(line)

    if not current_macro and __apply_macros(line):
      debug(msg_prefix + 'macro replaced, get fresh line')
      continue

    matches = RE_COMMENT.match(line)
    if matches:
      continue

    msg_prefix = 'pass #1: %s:%s: ' % (os.path.split(buff.filename)[1], buff.lineno)

    matches = RE_IFDEF.match(line)
    if matches:
      var = matches.groupdict()['var']

      debug(msg_prefix + 'ifdef %s', var)

      ifs.append((True, var))

      if var in defines:
        debug(msg_prefix + 'defined, continue processing')
        continue

      __fast_forward()
      continue

    matches = RE_IFNDEF.match(line)
    if matches:
      var = matches.groupdict()['var']

      debug(msg_prefix + 'ifndef %s', var)

      ifs.append((False, var))

      if var not in defines:
        debug(msg_prefix + 'not defined, continue processing')
        continue

      __fast_forward()
      continue

    matches = RE_ENDIF.match(line)
    if matches:
      debug(msg_prefix + 'removing the last conditional from stack: %s', ifs[-1])

      ifs.pop()
      continue

    matches = RE_ELSE.match(line)
    if matches:
      defined, var = ifs.pop()

      debug(msg_prefix + 'previous block was "%s %s"', 'ifdef' if defined is True else 'ifndef', var)

      ifs.append((not defined, var))

      if defined and var in defines:
        __fast_forward()
        continue

      debug(msg_prefix + 'continue processing')
      continue

    matches = RE_INCLUDE.match(line)
    if matches:
      matches = matches.groupdict()

      if 'file' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.include directive without path')

      debug(msg_prefix + 'include: file=%s', matches['file'])

      with open(matches['file'], 'r') as f_in:
        replace = f_in.read()

      buff.put_buffer(replace, filename = matches['file'])

      continue

    matches = RE_VAR_DEF.match(line)
    if matches:
      matches = matches.groupdict()

      v_name = matches.get('var_name', None)
      v_body = matches.get('var_body', None)

      if not v_name or not v_body:
        raise buff.get_error(IncompleteDirectiveError, 'bad variable definition')

      debug(msg_prefix + 'variable defined: name=%s, value=%s', v_name, v_body)

      defs[re.compile(r'\$%s' % v_name)] = v_body.strip()

      continue

    matches = RE_MACRO_DEF.match(line)
    if matches:
      matches = matches.groupdict()

      m_name = matches.get('macro_name', None)
      m_params = matches.get('macro_params', None)

      if not m_name:
        raise buff.get_error(IncompleteDirectiveError, 'bad macro definition')

      debug(msg_prefix + 'macro defined: name=%s', m_name)

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

        current_macro['pattern'] = re.compile(r'^\s*\$%s\s+%s\s*(?:[;/#].*)?$' % (m_name, arg_patterns), re.MULTILINE)

      else:
        current_macro['pattern'] = re.compile(r'\s*\$%s' % m_name)

      continue

    matches = RE_MACRO_END.match(line)
    if matches:
      if not current_macro:
        raise buff.get_error(AssemblerError, 'closing non-existing macro')

      macros[current_macro['pattern']] = current_macro
      debug(msg_prefix + 'macro definition closed: name=%s', current_macro['name'])
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
        flags = matches.get('flags', None)
        section_type = SectionTypes.TEXT if flags and 'x' in flags else SectionTypes.DATA

        section = sections_pass1[s_name] = Section(s_name, section_type, flags)
        debug(msg_prefix + 'section %s created', s_name)

      curr_section = sections_pass1[s_name]

      if curr_section.type == SectionTypes.TEXT:
        text_section = curr_section
        debug(msg_prefix + 'text section changed to %s', s_name)
      else:
        data_section = curr_section
        debug(msg_prefix + 'data section changed to %s', s_name)

      continue

    matches = RE_DATA.match(line)
    if matches:
      matches = matches.groupdict()

      curr_section = data_section = sections_pass1[matches['name'] if 'name' in matches and matches['name'] else '.data']
      debug(msg_prefix + 'data section is %s', data_section.name)
      continue

    matches = RE_TEXT.match(line)
    if matches:
      matches = matches.groupdict()

      curr_section = text_section = sections_pass1[matches['name'] if 'name' in matches and matches['name'] else '.text']
      debug(msg_prefix + 'text section is %s', text_section.name)
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
        raise buff.get_error(AssemblerError, 'Too many data labels: %s' % labels)

      var.name = labels[0] if labels else None
      var.close()

      debug(msg_prefix + 'record byte value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_INT.match(line)
    if matches:
      var = IntSlot()
      __parse_int(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: %s' % labels)

      var.name = labels[0] if labels else None
      var.close()

      debug(msg_prefix + 'record int value: name=%s, value=%s, refers_to=%s', var.name, var.value, var.refers_to)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_ASCII.match(line)
    if matches:
      var = AsciiSlot()
      __parse_ascii(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: %s' % labels)

      var.name = labels[0] if labels else None
      var.close()

      debug(msg_prefix + 'record ascii value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_STRING.match(line)
    if matches:
      var = StringSlot()
      __parse_string(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: %s' % labels)

      var.name = labels[0] if labels else None
      var.close()

      debug(msg_prefix + 'record string value: name=%s, value=%s', var.name, var.value)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_SPACE.match(line)
    if matches:
      var = SpaceSlot()
      __parse_space(var, matches)

      if len(labels) > 1:
        raise buff.get_error(AssemblerError, 'Too many data labels: %s' % labels)

      var.name = labels[0] if labels else None
      var.close()

      debug(msg_prefix + 'record space: name=%s, value=%s', var.name, var.size)
      data_section.content.append(var)

      labels = []
      continue

    matches = RE_SET.match(line)
    if matches:
      matches = matches.groupdict()

      if 'name' not in matches:
        raise buff.get_error(IncompleteDirectiveError, '.set directive without variable')

      name = matches['name']

      if matches.get('current', None):
        value = (curr_section.name, UInt16(curr_section.ptr.u16))

      elif matches.get('value_dec', None):
        value = int(matches['value_dec'])

      elif matches.get('value_hex', None):
        value = int(matches['value_hex'], base = 16)

      elif matches.get('value_label', None):
        value = matches['value_label']

      else:
        raise buff.get_error(IncompleteDirectiveError, '.set directive with unknown value')

      debug(msg_prefix + 'set variable: name=%s, value=%s', name, value)
      variables[name] = value

      continue

    if line.endswith(':'):
      label = Label(line.strip()[:-1], curr_section, buff.filename, buff.lineno)
      labels.append(label)

      debug(msg_prefix + 'record label: name=%s', label.name)
      continue

    debug(msg_prefix + 'line: %s', line)

    # label, instruction, 2nd pass flags
    emited_inst = None

    # Find instruction descriptor
    line = line.strip()

    for desc in instruction_set.instructions:
      debug(msg_prefix + 'pattern: %s', desc.pattern.pattern)
      if not desc.pattern.match(line):
        continue
      break

    else:
      raise buff.get_error(AssemblerError, 'Unknown pattern: line="%s"' % line)

    # pylint: disable-msg=W0631
    emited_inst = desc.emit_instruction(line)
    emited_inst.desc = desc

    if len(labels):
      text_section.content.append((labels, emited_inst))

    else:
      text_section.content.append((None, emited_inst))

    labels = []

    debug(msg_prefix + 'emitted instruction: %s', emited_inst.desc.instruction_set.disassemble_instruction(emited_inst))

    if isinstance(desc, cpu.instructions.Inst_SIS):
      debug(msg_prefix + 'switching istruction set: inst_set=%s', emited_inst.immediate)

      instruction_set = cpu.instructions.get_instruction_set(emited_inst.immediate)

  for s_name, section in sections_pass1.items():
    debug('pass #1: section %s', s_name)

    if section.type == SectionTypes.TEXT:
      for labeled, inst in section.content:
        debug('pass #1: inst=%s, labeled=%s', inst, labeled)

    else:
      for var in section.content:
        debug('pass #1: %s', var)

  debug('Pass #2')

  sections_pass2 = {}
  references = {}
  base_ptr = UInt16(base_address.u16)

  for s_name, p1_section in sections_pass1.items():
    section = sections_pass2[s_name] = Section(s_name, p1_section.type, p1_section.flags)

  symtab = sections_pass2['.symtab']

  for s_name, section in sections_pass2.items():
    p1_section = sections_pass1[s_name]

    # pylint: disable-msg=E1101
    # Instance of 'UInt16' has no 'u16' member
    section.base = UInt16(base_ptr.u16)
    section.ptr  = UInt16(base_ptr.u16)

    debug('pass #2: section %s - base=%s', section.name, ADDR_FMT(section.base.u16))

    if section.type == SectionTypes.SYMBOLS:
      continue

    if section.type == SectionTypes.DATA:
      for var in p1_section.content:
        ptr_prefix = 'pass #2: ' + ADDR_FMT(section.ptr.u16) + ': '

        debug(ptr_prefix + str(var))

        if var.name:
          var.section = section
          var.section_ptr = UInt16(section.ptr.u16)
          references['&' + var.name.name] = var

          symtab.content.append(var)

        if var.refers_to:
          refers_to = var.refers_to

          if isinstance(refers_to, types.TupleType):
            var.value = sections_pass2[refers_to[0]].base.u16 + refers_to[1].u16
            var.refers_to = None
            var.close()

            debug(ptr_prefix + 'reference "%s" replaced with %s', refers_to, ADDR_FMT(var.value))

          elif refers_to not in references:
            debug(ptr_prefix  + 'unresolved reference to %s', refers_to)

          else:
            refers_to_addr = references[refers_to].section_ptr.u16

            var.value = refers_to_addr
            var.refers_to = None
            var.close()

            debug(ptr_prefix + 'reference "%s" replaced with %s', refers_to, ADDR_FMT(refers_to_addr))

        if type(var) == IntSlot:
          if var.value:
            section.content.append(UInt8(var.value.u16 & 0x00FF))
            section.content.append(UInt8((var.value.u16 & 0xFF00) >> 8))
            debug(ptr_prefix + 'value stored')

          else:
            section.content.append(var)
            debug(ptr_prefix + 'value missing - reserve space, fix in next pass')

          section.ptr.u16 += 2

        elif type(var) == ByteSlot:
          section.content.append(UInt8(var.value.u8))
          section.ptr.u16 += var.size.u16
          debug(ptr_prefix + 'value stored')

        elif type(var) == AsciiSlot or type(var) == StringSlot:
          for i in range(0, var.size.u16):
            section.content.append(var.value[i])
            section.ptr.u16 += 1

          if var.size.u16 % 2 != 0:
            section.content.append(UInt8(0))
            section.ptr.u16 += 1

          debug(ptr_prefix + 'value stored')

        elif type(var) == SpaceSlot:
          section.content.append(var)
          section.ptr.u16 += var.size.u16
          debug(ptr_prefix + 'value stored')

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
            debug(ptr_prefix + 'label entry "%s" created', label)

        if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to:
          if inst.refers_to in references:
            refers_to_var = references[inst.refers_to]
            refers_to_addr = refers_to_var.section_ptr.u16
            if refers_to_var.section.type == SectionTypes.TEXT:
              refers_to_addr -= (inst.address.u16 + 4)

            inst.desc.fix_refers_to(inst, refers_to_addr)
            debug(ptr_prefix + 'reference "%s" replaced with %s', refers_to_var.name, ADDR_FMT(refers_to_addr))

          else:
            debug(ptr_prefix + 'reference "%s" unknown, fix in the next pass', inst.refers_to)

        section.content.append(inst)
        debug(ptr_prefix + inst.desc.instruction_set.disassemble_instruction(inst))
        section.ptr.u16 += 4

    base_ptr.u16 = align_to_next_mmap(section.ptr.u16) if mmapable_sections else align_to_next_page(section.ptr.u16)

  debug('Pass #3')

  sections_pass3 = {}

  for s_name, p2_section in sections_pass2.items():
    debug('pass #3: section %s', p2_section.name)

    section = Section(s_name, p2_section.type, p2_section.flags)
    sections_pass3[s_name] = section

    section.base = UInt16(p2_section.base.u16)
    section.ptr  = UInt16(section.base.u16)

    for item in p2_section.content:
      ptr_prefix = 'pass #3: ' + ADDR_FMT(section.ptr.u16) + ': '

      if section.type == SectionTypes.SYMBOLS:
        pass

      elif type(item) == IntSlot and item.refers_to:
        debug(ptr_prefix + 'fix reference: %s', item)

        if item.refers_to not in references:
          raise buff.get_error(AssemblerError, 'Unknown reference: name=%s' % item.refers_to)

        item.value = references[item.refers_to].section_ptr.u16
        debug(ptr_prefix + 'reference replaced with %s', ADDR_FMT(item.value))
        item.refers_to = None
        item.close()

        item = [UInt8(item.value.u16 & 0x00FF), UInt8((item.value.u16 & 0xFF00) >> 8)]

      elif hasattr(item, 'refers_to') and item.refers_to:
        debug(ptr_prefix + 'fix reference: %s', item)

        if item.refers_to not in references:
          raise buff.get_error(AssemblerError, 'No such label: name=%s' % item.refers_to)

        refers_to_var = references[item.refers_to]
        refers_to_addr = refers_to_var.section_ptr.u16
        debug(ptr_prefix + 'raw addr: %s', ADDR_FMT(refers_to_addr))
        if item.desc.relative_address is True:
          debug(ptr_prefix + 'convert to relative address')
          refers_to_addr -= (item.address.u16 + 4)

        item.desc.fix_refers_to(item, refers_to_addr)
        debug(ptr_prefix + 'referred addr %s', ADDR_FMT(refers_to_var.section_ptr.u16))
        debug(ptr_prefix + 'reference "%s" replaced with %s', refers_to_var.name, ADDR_FMT(refers_to_addr))

      debug(ptr_prefix + str(item))

      if not isinstance(item, types.ListType):
        item = [item]

      for i in item:
        section.content.append(i)
        section.ptr.u16 += sizeof(i)

    debug('pass #3: section %s finished: %s', section.name, section)

  debug('Bytecode sections:')
  for s_name, section in sections_pass3.items():
    debug(str(section))

  debug('Bytecode translation completed')

  return sections_pass3
