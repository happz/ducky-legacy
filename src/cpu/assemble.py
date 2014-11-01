#!/usr/bin/python

import optparse
import struct
import sys
import types

import cpu
import irq
import io
import mm

from mm import UInt8, UInt16, UINT8_FMT, UINT16_FMT, SEGM_FMT, ADDR_FMT, SIZE_FMT, PAGE_MASK, PAGE_SHIFT, PAGE_SIZE
from cpu.errors import CPUException

from util import debug, info, warn

def align_to_next_page(addr):
  return (((addr & PAGE_MASK) >> PAGE_SHIFT) + 1) * PAGE_SIZE

def translate_buffer(buff, csb = None, dsb = None):
  csb = csb or UInt16(0)

  cs_pass1  = []
  ds_pass1 = []
  symbols = {}

  debug('Pass #1')

  labeled = []

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
      symbols[v_name] = variable_desc
      ds_pass1.append(variable_desc)

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

  while len(buff):
    line = __get_line()

    if not line:
      break

    # starts new object
    if line.startswith('.type'):
      v_name, v_type = __expand_pseudoop(line, 2)

      if v_type == 'function':
        __handle_symbol_function()

      else:
        __handle_symbol_variable(v_name, v_type)

      continue

    if line.endswith(':'):
      label = line[:-1]
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
      cs_pass1.append((labels, emited_inst))

    else:
      cs_pass1.append((None, emited_inst))

    labels = []

    debug('emitted instruction: %s' % cpu.instructions.disassemble_instruction(emited_inst))

  for v_name, v_size, v_value, v_type in ds_pass1:
    debug('Data entry: v_name=%s, v_size=%u"' % (v_name, v_size.u16))

  for ins in cs_pass1:
    debug('Instruction: labeled=%s, ins=%s' % ins)

  cs_pass2 = []
  csp = UInt16(csb.u16)

  ds_pass2 = []
  dsb = dsb or UInt16(align_to_next_page(csb.u16 + len(cs_pass1) * 2))
  dsp = UInt16(dsb.u16)

  debug('CSB: %s' % ADDR_FMT(csb.u16))
  debug('DSB: %s' % ADDR_FMT(dsb.u16))

  references = {}
  symbols = []

  debug('Pass #2')

  pass3_required = False

  for v_name, v_size, v_value, v_type in ds_pass1:
    references['&' + v_name] = UInt16(dsp.u16)
    symbols.append((v_name, dsp.u16, v_size, v_type))

    debug('%s: data entry %s, size %s, type %s' % (ADDR_FMT(dsp.u16), v_name, SIZE_FMT(v_size.u16), type(v_value)))

    if type(v_value) == UInt16:
      ds_pass2.append(UInt8(v_value.u16 & 0x00FF))
      ds_pass2.append(UInt8((v_value.u16 & 0xFF00) >> 8))
      dsp.u16 += 2

    elif type(v_value) == UInt8:
      ds_pass2.append(UInt8(v_value.u8))
      ds_pass2.append(UInt8(0))
      dsp.u16 += 2

    elif type(v_value) == types.ListType:
      for i in range(0, v_size.u16):
        ds_pass2.append(v_value[i])
        dsp.u16 += 1

      if v_size.u16 % 2 != 0:
        ds_pass2.append(UInt8(0))
        dsp.u16 += 1

  for labeled, inst in cs_pass1:
    csp_str = ADDR_FMT(csp.u16)

    if labeled:
      for label in labeled:
        references[label] = UInt16(csp.u16)
        debug(csp_str, 'label entry "%s" created' % label)

    if inst.desc.operands and ('i' in inst.desc.operands or 'j' in inst.desc.operands) and hasattr(inst, 'refers_to') and inst.refers_to:
      if inst.refers_to in references:
        refers_to = inst.refers_to
        inst.desc.fix_refers_to(inst, references[inst.refers_to].u16)
        debug(csp_str, 'reference "%s" replaced with %s' % (refers_to, ADDR_FMT(references[refers_to].u16)))

      else:
        pass3_required = True
        debug(csp_str, 'reference "%s" unknown, fix in the next pass' % inst.refers_to)

    cs_pass2.append(inst)

    debug(csp_str, cpu.instructions.disassemble_instruction(inst))
    csp.u16 += 4

  if pass3_required:
    debug('Pass #3')

    cs_pass3 = []

    for inst in cs_pass2:
      if hasattr(inst, 'refers_to') and inst.refers_to:
        refers_to = inst.refers_to

        inst.desc.fix_refers_to(inst, references[inst.refers_to].u16)
        debug(csp_str, 'reference "%s" replaced with %s' % (refers_to, ADDR_FMT(references[refers_to].u16)))

      cs_pass3.append(inst)

    ds_pass3 = ds_pass2[:]

  else:
    cs_pass3 = cs_pass2[:]
    ds_pass3 = ds_pass2[:]

  debug('CSB: %s, size: %s' % (ADDR_FMT(csb.u16), SIZE_FMT(len(cs_pass3))))
  debug('DSB: %s, size: %s' % (ADDR_FMT(dsb.u16), SIZE_FMT(len(ds_pass3))))

  info('Bytecode translation completed')

  return (
    (csb, cs_pass3),
    (dsb, ds_pass2),
    symbols
  )
