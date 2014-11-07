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
from cpu.errors import CPUException

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

  def __len__(self):
    # pylint: disable-msg=E1101
    # Instance of 'UInt16' has no 'u16' member
    return self.ptr.u16 - self.base.u16

class TextSection(Section):
  def __init__(self, s_name, flags = None):
    super(TextSection, self).__init__(s_name, SectionTypes.TEXT, flags or 'rx')

class DataSection(Section):
  def __init__(self, s_name, flags = None):
    super(DataSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rw')

class BssSection(Section):
  def __init__(self, s_name, flags = None):
    super(BssSection, self).__init__(s_name, SectionTypes.DATA, flags or 'rwb')

def translate_buffer(buff, base_address = None):
  base_address = base_address or UInt16(0)

  sections_pass1 = {
    '.text': TextSection('.text'),
    '.data': DataSection('.data'),
    '.bss':  BssSection('.bss'),
    '.symtab': Section('.symtab', SectionTypes.SYMBOLS, '')
  }

  debug('Pass #1')

  labeled = []

  def __get_refers_to_operand(inst):
    r_address = references[inst.refers_to].u16

    if inst.refers_to.startswith('@'):
      r_address -= (inst.address.u16 + 4)

    return r_address

  def __get_line():
    while len(buff):
      line = buff.pop(0)

      if not line:
        continue

      line = line.strip()

      # Skip comments and empty lines
      if not line or line[0] in ('#', '/'):
        continue

      debug('new line from buffer: %s' % line)
      return line

    else:
      return None

  def __expand_pseudoop(line, tokens):
    # Don't use line.split() - it will split by spaces all strings, even variable's value...
    first_space = line.index(' ')

    if   tokens == 1:
      return (line[first_space:].strip(),)

    elif tokens == 2:
      second_space = line.index(' ', first_space + 1)

      return (line[first_space:second_space].strip()[:-1], line[second_space:].strip())

    else:
      raise CPUException('Unhandled number of tokens: %s - %i' % (line, tokens))

  def __handle_symbol_variable(v_name, v_type):
    v_size  = None # if not set, default value will be set according to the type
    v_value = None # if not set, default value will be used

    def __emit_variable(v_name, v_size, v_value):
      if v_type == 'int':
        v_value = v_value or '0'
        v_value = UInt16(int(v_value))
        v_size  = UInt16(2)

      elif v_type == 'char':
        v_value = v_value or '\0'
        v_value = UInt8(ord(v_value))
        v_size  = UInt16(1)

      elif v_type == 'string':
        v_value = v_value or ""
        v_value = [UInt8(ord(c)) for c in v_value] + [UInt8(0)]
        v_size  = UInt16(len(v_value))

      variable_desc = (v_name, v_size, v_value, v_type)
      data_section.content.append(variable_desc)

    while len(buff):
      line = __get_line()

      handled_pseudoops = ('.size', '.%s' % v_type)

      if not line or line.startswith('.type') or not line.startswith(handled_pseudoops):
        # create variable
        __emit_variable(v_name, v_size, v_value)

        # return current line and start from the beginning
        buff.insert(0, line)
        return

      if line.startswith('.size'):
        v_size = __expand_pseudoop(line, 1)[0]

      elif line.startswith('.%s' % v_type):
        if v_type == 'int':
          v_value = int(__expand_pseudoop(line, 1)[0])
        elif v_type == 'string':
          v_value = __expand_pseudoop(line, 1)[0][1:-1] # omit enclosing quotes
        else:
          raise CPUException('Unknown variable type: %s' % v_type)

  def __handle_symbol_function():
    pass

  labels = []

  debug('Pass #1: text section is .text')
  debug('Pass #1: data section is .data')

  text_section = sections_pass1['.text']
  data_section = sections_pass1['.data']

  while len(buff):
    line = __get_line()

    if not line:
      break

    if line.startswith('.section'):
      matches = re.compile(r'.section\s+(?P<name>\.[a-zA-z0-9_])(?P<flags>,[rwxb]*)?').match(line).groupdict()

      s_name = matches['name']

      if s_name not in sections_pass1:
        data_section = sections_pass1[s_name] = Section(s_name, matches.get('flags', None))
        debug('Pass #1: section %s created' % s_name)

      continue

    if line.startswith('.data'):
      matches = re.compile(r'.data\s+(?P<name>\.[a-zA-z0-9_])?').match(line)
      matches = matches.groupdict() if matches else {}
      data_section = sections_pass1[matches.get('name', None) or '.data']
      debug('Pass #1: data section is %s' % data_section.name)
      continue

    if line.startswith('.text'):
      matches = re.compile(r'.text\s+(?P<name>\.[a-zA-z0-9_])?').match(line)
      matches = matches.groupdict() if matches else {}
      text_section = sections_pass1[matches.get('name', None) or '.text']
      debug('Pass #1: text section is %s' % text_section.name)
      continue

    if line.startswith('.comm'):
      matches = re.compile(r'.comm\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?P<size>\d+)').match(line).groupdict()

      data_section.content.append((matches['name'], UInt16(int(matches['size'])), None, None))

    if line.startswith('.type'):
      matches = re.compile(r'.type\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*),\s*(?P<type>(?:char|int|string))').match(line).groupdict()

      if matches['type'] == 'function':
        __handle_symbol_function()

      else:
        __handle_symbol_variable(matches['name'], matches['type'])

      continue

    if line.endswith(':'):
      label = '@' + line[:-1]
      debug('label encountered: "%s"' % label)
      labels.append(label)
      continue

    debug('line: %s' % line)

    # label, instruction, 2nd pass flags
    emited_inst = None

    # Find instruction descriptor
    for desc in cpu.instructions.INSTRUCTIONS:
      if not desc.pattern.match(line):
        continue
      break

    else:
      raise CPUException('Unknown pattern: line="%s"' % line)

    # pylint: disable-msg=W0631
    emited_inst = desc.emit_instruction(line)
    emited_inst.desc = desc

    if len(labels):
      text_section.content.append((labels, emited_inst))

    else:
      text_section.content.append((None, emited_inst))

    labels = []

    debug('emitted instruction: %s' % cpu.instructions.disassemble_instruction(emited_inst))

  for s_name, section in sections_pass1.items():
    debug('Pass #1: section %s' % s_name)

    if section.type == SectionTypes.TEXT:
      for ins in section.content:
        debug('Instruction: labeled=%s, ins=%s' % ins)
    else:
      for v_name, v_size, v_value, v_type in section.content:
        debug('Data entry: v_name=%s, v_size=%u"' % (v_name, v_size.u16))

  debug('Pass #2')

  sections_pass2 = {}
  references = {}
  pass3_required = False
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

    debug('Pass #2: section %s - base=%s' % (section.name, ADDR_FMT(section.base.u16)))

    if section.type == SectionTypes.SYMBOLS:
      continue

    if section.type == SectionTypes.DATA:
      for v_name, v_size, v_value, v_type in p1_section.content:
        ptr_prefix = ADDR_FMT(section.ptr.u16)

        debug(ptr_prefix, 'name=%s, size=%s, type=%s' % (v_name, SIZE_FMT(v_size.u16), v_type))

        references['&' + v_name] = UInt16(section.ptr.u16)
        symtab.content.append((v_name, v_type, v_size, section.name, UInt16(section.ptr.u16)))

        if 'b' in section.flags:
          section.ptr.u16 += v_size
          continue

        if type(v_value) == UInt16:
          section.content.append(UInt8(v_value.u16 & 0x00FF))
          section.content.append(UInt8((v_value.u16 & 0xFF00) >> 8))
          section.ptr.u16 += 2

        elif type(v_value) == UInt8:
          section.content.append(UInt8(v_value.u8))
          section.content.append(UInt8(0))
          section.ptr.u16 += 2

        elif type(v_value) == types.ListType:
          for i in range(0, v_size.u16):
            section.content.append(v_value[i])
            section.ptr.u16 += 1

          if v_size.u16 % 2 != 0:
            section.content.append(UInt8(0))
            section.ptr.u16 += 1

    if section.type == SectionTypes.TEXT:
      for labeled, inst in p1_section.content:
        ptr_prefix = ADDR_FMT(section.ptr.u16)

        inst.address = UInt16(section.ptr.u16)

        if labeled:
          for label in labeled:
            if not label.startswith('@.L') and not label.startswith('@__'):
              symtab.content.append((label[1:], 'function', UInt16(0), section.name, UInt16(section.ptr.u16)))

            references[label] = UInt16(section.ptr.u16)
            debug(ptr_prefix, 'label entry "%s" created' % label)

        if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to:
          if inst.refers_to in references:
            refers_to = inst.refers_to

            refers_to_operand = __get_refers_to_operand(inst)

            inst.desc.fix_refers_to(inst, refers_to_operand)
            debug(ptr_prefix, 'reference "%s" replaced with %s' % (refers_to, refers_to_operand))

          else:
            pass3_required = True
            debug(ptr_prefix, 'reference "%s" unknown, fix in the next pass' % inst.refers_to)

        section.content.append(inst)
        debug(ptr_prefix, cpu.instructions.disassemble_instruction(inst))
        section.ptr.u16 += 4

    base_ptr.u16 += align_to_next_page(section.ptr.u16 - section.base.u16)

  sections_pass3 = sections_pass2

  if pass3_required:
    debug('Pass #3')

    for s_name, section in sections_pass3.items():
      for inst in section.content:
        if hasattr(inst, 'refers_to') and inst.refers_to:
          refers_to = inst.refers_to

          refers_to_operand = __get_refers_to_operand(inst)

          inst.desc.fix_refers_to(inst, refers_to_operand)
          debug('reference "%s" replaced with %s' % (refers_to, refers_to_operand))

  debug('Bytecode sections:')
  for s_name, section in sections_pass3.items():
    debug('name=%s, base=%s, size=%s, flags=%s' % (section.name, ADDR_FMT(section.base.u16), SIZE_FMT(len(section)), section.flags))

  info('Bytecode translation completed')

  return sections_pass3
