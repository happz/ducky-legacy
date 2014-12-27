#!/usr/bin/python

import optparse
import re
import struct
import sys
import types

import cpu
import mm

from mm import UInt8, UInt16, UINT8_FMT, UINT16_FMT, SEGM_FMT, ADDR_FMT, SIZE_FMT, PAGE_MASK, PAGE_SHIFT, PAGE_SIZE
from mm.binary import SectionTypes
from cpu.errors import CompilationError

from util import debug, info, warn

def align_to_next_page(addr):
  return (((addr & PAGE_MASK) >> PAGE_SHIFT) + 1) * PAGE_SIZE

class Section(object):
  def __init__(self, s_name, s_type, s_flags):
    super(Section, self).__init__()

    self.name    = s_name
    self.type    = s_type
    self.flags   = s_flags
    self.content = []

    self.base = UInt16(0)
    self.ptr  = UInt16(0)

    self.offset = 0
    self.length = 0

  def __len__(self):
    # pylint: disable-msg=E1101
    # Instance of 'UInt16' has no 'u16' member
    return self.ptr.u16 - self.base.u16

class TextSection(Section):
  def __init__(self, s_name, flags = None):
    super(TextSection, self).__init__(s_name, SectionTypes.TEXT, flags or 'rx')

class RODataSection(Section):
  def __init__(self, s_name, flags = None):
    super(RODataSection, self).__init__(s_name, SectionTypes.DATA, flags or 'r')

class DataSection(Section):
  def __init__(self, s_name, flags = None):
    super(DataSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rw')

class BssSection(Section):
  def __init__(self, s_name, flags = None):
    super(BssSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rwb')

def preprocess_buffer(buff):
  debug('preprocess_buffer')

  r_comment = re.compile(r'^\s*[/;*].*?$', re.MULTILINE)

  buff = r_comment.sub('', buff)

  r_var_def   = re.compile(r'^\.def\s+(?P<var_name>[a-zA-Z][a-zA-Z0-9_]*):\s*(?P<var_body>.*?)$', re.MULTILINE)
  r_macro_def = re.compile(r'^\.macro\s+(?P<macro_name>[a-zA-Z][a-zA-Z0-9_]*)(?:\s+(?P<macro_params>.*?))?:$(?P<macro_body>.*?)^.end$', re.MULTILINE | re.DOTALL)

  vars = r_var_def.findall(buff)

  while True:
    matches = r_var_def.search(buff)
    if not matches:
      break

    matches = matches.groupdict()
    v_name = matches['var_name']
    v_body = matches['var_body']

    debug('variable found: %s' % v_name)

    r_remove = re.compile(r'^\.def\s+%s:\s+.*?$' % v_name, re.MULTILINE)
    r_replace = re.compile(r'\$%s' % v_name)

    v_body = v_body.strip()

    buff = r_remove.sub('', buff)
    buff = r_replace.sub(v_body, buff)

  while True:
    matches = r_macro_def.search(buff)
    if not matches:
      break

    matches = matches.groupdict()
    m_name = matches['macro_name']
    m_params = matches['macro_params']
    m_body = matches['macro_body']

    debug('macro found: %s' % m_name)

    params = [p.strip() for p in m_params.strip().split(',')] if m_params else []

    r_remove  = re.compile(r'^.macro\s+%s(?:\s+.*?)?:$.*?^.end$' % m_name, re.MULTILINE | re.DOTALL)
    buff = r_remove.sub('', buff)

    if params and len(params[0]):
      def __replace_usage(m):
        m_body_with_args = m_body

        for i in range(1, len(params) + 1):
          m_body_with_args = re.sub('#%s' % params[i - 1], m.group(i), m_body_with_args)

        return m_body_with_args

      arg_pattern = r'(?P<arg%i>(?:".*?")|(?:.*?))'
      arg_patterns = ',\s*'.join([arg_pattern % i for i in range(0, len(params))])
      r_usage = re.compile(r'\$%s\s+%s[\s$]' % (m_name, arg_patterns), re.MULTILINE)

      buff = r_usage.sub(__replace_usage, buff)

    else:
      r_replace = re.compile(r'\$%s' % m_name)

      buff = r_replace.sub(m_body, buff)

  return buff

class Label(object):
  def __init__(self, name, section):
    super(Label, self).__init__()

    self.name = name
    self.section = section

  def __repr__(self):
    return '<label %s in section %s>' % (self.name, self.section.name)

class DataSlot(object):
  def __init__(self):
    super(DataSlot, self).__init__()

    self.name  = None
    self.size  = None
    self.refers_to = None
    self.value = None

    self.section = None
    self.section_ptr = None

  def close(self):
    pass

class ByteSlot(DataSlot):
  def close(self):
    self.value = UInt8(self.value or 0)
    self.size = UInt16(1)

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

class FunctionSlot(DataSlot):
  symbol_type = mm.binary.SymbolDataTypes.FUNCTION

  def close(self):
    self.size = UInt16(0)

def sizeof(o):
  if isinstance(o, DataSlot):
    return o.size.u16

  import ctypes

  if isinstance(o, ctypes.LittleEndianStructure):
    return ctypes.sizeof(o)

  return None

def translate_buffer(buff, base_address = None):
  buff = preprocess_buffer(buff)

  base_address = base_address or UInt16(0)

  sections_pass1 = {
    '.text': TextSection('.text'),
    '.rodata': RODataSection('.rodata'),
    '.data': DataSection('.data'),
    '.bss':  BssSection('.bss'),
    '.symtab': Section('.symtab', SectionTypes.SYMBOLS, '')
  }

  buff = buff.split('\n')

  debug('Pass #1')

  labeled = []

  def __get_refers_to_operand(inst):
    r_address = references[inst.refers_to].section_ptr.u16

    if inst.refers_to.startswith(''):
      r_address -= (inst.address.u16 + 4)

    return r_address

  def __get_line():
    while len(buff):
      line = buff.pop(0)

      if not line:
        continue

      line = line.strip()

      # Skip comments and empty lines
      if not line or line[0] in ('#', '/', ';'):
        continue

      debug('new line from buffer: %s' % line)
      return line

    else:
      return None

  def __parse_int(var, line):
    matches = r_int.match(line).groupdict()

    if 'value_dec' in matches and matches['value_dec']:
      var.value = int(matches['value_dec'])

    elif 'value_hex' in matches and matches['value_hex']:
      var.value = int(matches['value_hex'], base = 16)

    elif 'value_var' in matches and matches['value_var']:
      referred_var = variables[matches['value_var']]

      if type(referred_var) is types.IntType:
        var.value = referred_var
      else:
        var.refers_to = referred_var

    elif 'value_label' in matches and matches['value_label']:
      var.refers_to = matches['value_label']

    else:
      assert False, matches

  def __parse_ascii(var, line):
    matches = r_ascii.match(line).groupdict()

    if 'value' in matches and matches['value']:
      var.value = matches['value']

    else:
      assert False, matches

  def __parse_string(var, line):
    matches = r_string.match(line).groupdict()

    if 'value' in matches and matches['value']:
      var.value = matches['value']

    else:
      assert False, matches

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

    var.name = Label(v_name, curr_section)

    while len(buff):
      line = __get_line()

      handled_pseudoops = ('.size', '.%s' % v_type)

      if not line or line.startswith('.type') or not line.startswith(handled_pseudoops):
        # reserve variable
        var.close()
        data_section.content.append(var)

        # return current line and start from the beginning
        buff.insert(0, line)
        return

      if line.startswith('.size'):
        matches = r_size.match(line).groupdict()
        var.size = UInt16(int(matches['size']))

      elif line.startswith('.%s' % v_type):
        if v_type == 'int':
          __parse_int(var, line)

        elif v_type == 'ascii':
          __parse_ascii(var, line)

        elif v_type == 'string':
          __parse_string(var, line)

        else:
          raise CompilationError('Unknown variable type: %s' % v_type)

  r_ascii   = re.compile(r'\.ascii\s+"(?P<value>.*?)"')
  r_byte    = re.compile(r'\.byte\s+(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>(?:0)|(?:-?[1-9][0-9]*))|(?P<value_var>[a-zA-Z][a-zA-Z0-9_]*))')
  r_data    = re.compile(r'\.data\s+(?P<name>\.[a-z][a-z0-9_]*)?')
  r_int     = re.compile(r'\.int\s+(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_var>[a-zA-Z][a-zA-Z0-9_]*)|(?P<value_label>&[a-zA-Z][a-zA-Z0-9_]*))')
  r_section = re.compile(r'\.section\s+(?P<name>\.[a-zA-z0-9_]+)(?:,\s*(?P<flags>[rwxb]*))?')
  r_set     = re.compile(r'\.set\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?:(?P<value_hex>-?0x[a-fA-F0-9]+)|(?P<value_dec>0|(?:-?[1-9][0-9]*))|(?P<value_label>&[a-zA-Z][a-zA-Z0-9_]*))\s*$', re.MULTILINE)
  r_size    = re.compile(r'\.size\s+(?P<size>[1-9][0-9]*)')
  r_space   = re.compile(r'\.space\s+(?P<size>[1-9][0-9]*)')
  r_string  = re.compile(r'\.string\s+"(?P<value>.*?)"')
  r_text    = re.compile(r'\.text\s+(?P<name>\.[a-z][a-z0-9_]*)?')
  r_type    = re.compile(r'\.type\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?P<type>(?:char|byte|int|ascii|string))')

  labels = []
  variables = {}

  debug('Pass #1: text section is .text')
  debug('Pass #1: data section is .data')

  text_section = sections_pass1['.text']
  data_section = sections_pass1['.data']
  curr_section = text_section

  while len(buff):
    line = __get_line()

    if not line:
      break

    if line.startswith('.section'):
      matches = r_section.match(line).groupdict()

      s_name = matches['name']

      if s_name not in sections_pass1:
        data_section = sections_pass1[s_name] = Section(s_name, SectionTypes.DATA, matches.get('flags', None))
        debug('pass #1: section %s created' % s_name)

      curr_section = data_section = sections_pass1[s_name]
      debug('pass #1: data section changed to %s' % s_name)

      continue

    if line.startswith('.data'):
      matches = r_data.match(line)
      matches = matches.groupdict() if matches else {}

      curr_section = data_section = sections_pass1[matches.get('name', None) or '.data']
      debug('pass #1: data section is %s' % data_section.name)
      continue

    if line.startswith('.text'):
      matches = r_text.match(line)
      matches = matches.groupdict() if matches else {}

      curr_section = text_section = sections_pass1[matches.get('name', None) or '.text']
      debug('pass #1: text section is %s' % text_section.name)
      continue

    if line.startswith('.type '):
      matches = r_type.match(line).groupdict()

      if matches['type'] == 'function':
        __handle_symbol_function()

      else:
        __handle_symbol_variable(matches['name'], matches['type'])

      continue

    if line.startswith('.byte '):
      var = ByteSlot()
      matches = r_byte.match(line).groupdict()

      if 'value_dec' in matches and matches['value_dec']:
        var.value = int(matches['value_dec'])

      elif 'value_hex' in matches and matches['value_hex']:
        var.value = int(matches['value_hex'], base = 16)

      elif 'value_var' in matches and matches['value_var']:
        var.value = variables[matches['value_var']]

      else:
        assert False, matches

      assert len(labels) <= 1, 'Too many data labels: %s' % labels

      var.name = labels[0] if labels else None
      var.close()

      debug('pass #1: record byte value: name=%s, value=%s' % (var.name, var.value))
      data_section.content.append(var)

      labels = []
      continue

    if line.startswith('.int '):
      var = IntSlot()
      __parse_int(var, line)

      assert len(labels) <= 1, 'Too many data labels: %s' % labels

      var.name = labels[0] if labels else None
      var.close()

      debug('pass #1: record int value: name=%s, value=%s, refers_to=%s' % (var.name, var.value, var.refers_to))
      data_section.content.append(var)

      labels = []
      continue

    if line.startswith('.ascii '):
      var = AsciiSlot()
      __parse_ascii(var, line)

      assert len(labels) <= 1, 'Too many data labels: %s' % labels

      var.name = labels[0] if labels else None
      var.close()

      debug('pass #1: record ascii value: name=%s, value=%s' % (var.name, var.value))
      data_section.content.append(var)

      labels = []
      continue

    if line.startswith('.string '):
      var = StringSlot()
      __parse_string()

      assert len(labels) <= 1, 'Too many data labels: %s' % labels

      var.name = labels[0] if labels else None
      var.close()

      debug('pass #1: record string value: name=%s, value=%s' % (var.name, var.value))
      data_section.content.append(var)

      labels = []
      continue

    if line.startswith('.space '):
      var = AsciiSlot()
      matches = r_space.match(line).groupdict()

      var.value = ''.join(['\0' for _ in range(0, int(matches['size']))])

      assert len(labels) <= 1, 'Too many data labels: %s' % labels

      var.name = labels[0] if labels else None
      var.close()

      debug('pass #1: record space: name=%s, value=%s' % (var.name, var.size))
      data_section.content.append(var)

      labels = []
      continue

    if line.startswith('.set '):
      matches = r_set.match(line).groupdict()

      name = matches['name']

      if 'value_dec' in matches and matches['value_dec']:
        value = int(matches['value_dec'])

      elif 'value_hex' in matches and matches['value_hex']:
        value = int(matches['value_hex'], base = 16)

      elif 'value_label' in matches and matches['value_label']:
        value = matches['value_label']

      else:
        assert False, matches

      debug('pass #1: set variable: name=%s, value=%s' % (name, value))
      variables[name] = value

      continue

    if line.endswith(':'):
      label = Label(line[:-1], curr_section)
      labels.append(label)

      debug('pass #1: record label: name=%s' % label.name)
      continue

    debug('pass #1: line: %s' % line)

    # label, instruction, 2nd pass flags
    emited_inst = None

    # Find instruction descriptor
    for desc in cpu.instructions.INSTRUCTIONS:
      if not desc.pattern.match(line):
        continue
      break

    else:
      raise CompilationError('Unknown pattern: line="%s"' % line)

    # pylint: disable-msg=W0631
    emited_inst = desc.emit_instruction(line)
    emited_inst.desc = desc

    if len(labels):
      text_section.content.append((labels, emited_inst))

    else:
      text_section.content.append((None, emited_inst))

    labels = []

    debug('pass #1: emitted instruction: %s' % cpu.instructions.disassemble_instruction(emited_inst))

  for s_name, section in sections_pass1.items():
    debug('pass #1: section %s' % s_name)

    if section.type == SectionTypes.TEXT:
      for labeled, inst in section.content:
        debug('pass #1: inst=%s, labeled=%s' % (inst, labeled))

    else:
      for var in section.content:
        debug('pass #1:', var)

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

    debug('pass #2: section %s - base=%s' % (section.name, ADDR_FMT(section.base.u16)))

    if section.type == SectionTypes.SYMBOLS:
      continue

    if section.type == SectionTypes.DATA:
      for var in p1_section.content:
        ptr_prefix = 'pass #2: ' + ADDR_FMT(section.ptr.u16)

        debug(ptr_prefix, var)

        if var.name:
          var.section = section
          var.section_ptr = UInt16(section.ptr.u16)
          references['&' + var.name.name] = var

          symtab.content.append(var)

        if var.refers_to:
          refers_to = var.refers_to

          if refers_to not in references:
            debug(ptr_prefix, 'unresolved reference to %s' % refers_to)

          else:
            refers_to_addr = references[refers_to].section_ptr.u16

            var.value = refers_to_addr
            var.refers_to = None
            var.close()

            debug(ptr_prefix, 'reference "%s" replaced with %s' % (refers_to, ADDR_FMT(refers_to_addr)))

        if 'b' in section.flags:
          section.ptr.u16 += v_size
          continue

        if type(var) == IntSlot:
          if var.value:
            section.content.append(UInt8(var.value.u16 & 0x00FF))
            section.content.append(UInt8((var.value.u16 & 0xFF00) >> 8))
            debug(ptr_prefix, 'value stored')

          else:
            section.content.append(var)
            debug(ptr_prefix, 'value missing - reserve space, fix in next pass')

          section.ptr.u16 += 2

        elif type(var) == ByteSlot:
          section.content.append(UInt8(var.value.u8))
          section.ptr.u16 += var.size.u16
          debug(ptr_prefix, 'value stored')

        elif type(var) == AsciiSlot or type(var) == StringSlot:
          for i in range(0, var.size.u16):
            section.content.append(var.value[i])
            section.ptr.u16 += 1

          if var.size.u16 % 2 != 0:
            section.content.append(UInt8(0))
            section.ptr.u16 += 1

          debug(ptr_prefix, 'value stored')

    if section.type == SectionTypes.TEXT:
      for labeled, inst in p1_section.content:
        ptr_prefix = 'pass #2: ' + ADDR_FMT(section.ptr.u16)

        inst.address = UInt16(section.ptr.u16)

        if labeled:
          for label in labeled:
            var = FunctionSlot()
            var.name = label
            var.section = section
            var.section_ptr = UInt16(section.ptr.u16)
            var.close()

            symtab.content.append(var)

            references['&' + label.name] = var
            debug(ptr_prefix, 'label entry "%s" created' % label)

        if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to:
          if inst.refers_to in references:
            refers_to_var = references[inst.refers_to]
            refers_to_addr = refers_to_var.section_ptr.u16
            if refers_to_var.section.type == SectionTypes.TEXT:
              refers_to_addr -= (inst.address.u16 + 4)

            inst.desc.fix_refers_to(inst, refers_to_addr)
            debug(ptr_prefix, 'reference "%s" replaced with %s' % (refers_to_var.name, ADDR_FMT(refers_to_addr)))

          else:
            debug(ptr_prefix, 'reference "%s" unknown, fix in the next pass' % inst.refers_to)

        section.content.append(inst)
        debug(ptr_prefix, cpu.instructions.disassemble_instruction(inst))
        section.ptr.u16 += 4

    base_ptr.u16 += align_to_next_page(section.ptr.u16 - section.base.u16)

  debug('Pass #3')

  sections_pass3 = {}

  for s_name, p2_section in sections_pass2.items():
    debug('pass #3: section %s' % p2_section.name)

    section = Section(s_name, p2_section.type, p2_section.flags)
    sections_pass3[s_name] = section

    section.base = UInt16(p2_section.base.u16)
    section.ptr  = UInt16(section.base.u16)

    for item in p2_section.content:
      ptr_prefix = 'pass #3: ' + ADDR_FMT(section.ptr.u16)

      if section.type == SectionTypes.SYMBOLS:
        pass

      elif type(item) == IntSlot and item.refers_to:
        debug(ptr_prefix, 'fix reference: %s' % item)

        if item.refers_to not in references:
          raise CompilationError('Unknown reference: %s' % item.refers_to)

        item.value = references[item.refers_to].section_ptr.u16
        debug(ptr_prefix, 'reference replaced with %s' % ADDR_FMT(item.value))
        item.refers_to = None
        item.close()

        item = [UInt8(item.value.u16 & 0x00FF), UInt8((item.value.u16 & 0xFF00) >> 8)]

      elif hasattr(item, 'refers_to') and item.refers_to:
        debug(ptr_prefix, 'fix reference: %s' % item)

        if item.refers_to not in references:
          raise CompilationError('No such label: "%s"' % item.refers_to)

        refers_to_var = references[item.refers_to]
        refers_to_addr = refers_to_var.section_ptr.u16
        if refers_to_var.section.type == SectionTypes.TEXT:
          refers_to_addr -= (item.address.u16 + 4)

        item.desc.fix_refers_to(item, refers_to_addr)
        debug(ptr_prefix, 'referred addr %s' % ADDR_FMT(refers_to_var.section_ptr.u16))
        debug(ptr_prefix, 'reference "%s" replaced with %s' % (refers_to_var.name, ADDR_FMT(refers_to_addr)))

      debug(ptr_prefix, item)

      if type(item) != types.ListType:
        item = [item]

      for i in item:
        section.content.append(i)
        section.ptr.u16 += sizeof(i)

    debug('pass #3: section %s finished, size %s' % (section.name, len(section.content)))

  debug('Bytecode sections:')
  for s_name, section in sections_pass3.items():
    debug('name=%s, base=%s, items=%s, size=%s, flags=%s' % (section.name, ADDR_FMT(section.base.u16), len(section.content), SIZE_FMT(len(section)), section.flags))

  info('Bytecode translation completed')

  return sections_pass3
