#!/usr/bin/python

import optparse
import struct
import sys
import types

import cpu
import irq
import io
import mm
import cpu.instructions
import mm.binary

from mm import UInt8, UInt16
from cpu.instructions import ins2str
from cpu.errors import CPUException

from util import *

def align_to_next_page(addr):
  return (((addr & mm.PAGE_MASK) >> mm.PAGE_SHIFT) + 1) * mm.PAGE_SIZE

def compile_buffer(buffer, text_base = mm.MEM_FIRST_BOOT_IP, data_base = None):
  ins_pass1  = []
  data_pass1 = []

  debug('Pass #1')

  labeled = None

  for line in buffer:
    line = line.strip()
    if not line or line[0] == '#':
      continue

    if line.startswith('data'):
      comma_index = line.find(',')
      name = line[5:comma_index]
      value = line[comma_index + 3:-1]

      data_pass1.append((name, value))
      continue

    # label, instruction, 2nd pass flags
    emited_ins = None

    if line[-1] == ':':
      labeled = line[0:-1]
      continue

    # Find instruction descriptor
    for i in range(0, len(cpu.instructions.PATTERNS)):
      if not cpu.instructions.PATTERNS[i].match(line):
        continue
      ID = cpu.instructions.INSTRUCTIONS[i]
      break
    else:
      raise CPUException('Unknown pattern: line="%s"' % line)

    emited_ins = ID.emit_instruction(line)

    for i in range(0, len(emited_ins)):
      if labeled and i == 0:
        ins_pass1.append((labeled, emited_ins[i]))
      else:
        ins_pass1.append((None, emited_ins[i]))

    labeled = None

  for name, value in data_pass1:
    debug('Data entry: "%s"="%s"' % (name, value))

  for ins in ins_pass1:
    debug('Instruction: label=%s, ins=%s' % ins)

  cs = []
  csb = UInt16(text_base)
  csp = UInt16(csb.u16)

  ds = []
  dsb = UInt16(data_base or align_to_next_page(csb.u16 + len(ins_pass1) * 2))
  dsp = UInt16(dsb.u16)

  debug('CSB: 0x%X' % csb.u16)
  debug('DSB: 0x%X' % dsb.u16)

  references = {}

  symbols = []

  debug('Pass #2')

  for name, value in data_pass1:
    references['&' + name] = UInt16(dsp.u16)
    symbols.append(('&' + name, dsp.u16, UInt16(len(value)).u16))

    debug('0x%X: data entry "%s", size 0x%X' % (dsp.u16, name, len(value)))

    for i in range(0, len(value)):
      ds.append(UInt8(ord(value[i])))
      dsp.u16 += 1

  for label, ins in ins_pass1:
    csp_str = '0x%X:' % csp.u16

    if label:
      references[label] = UInt16(csp.u16)
      debug(csp_str, 'label entry "%s" created' % label)

    if type(ins) == types.StringType:
      cs.append(references[ins])
      debug(csp_str, 'reference "%s" replaced with 0x%X' % (ins, references[ins].u16))
    else:
      cs.append(ins)

      if type(ins) == cpu.instructions.InstructionBinaryFormat:
        debug(csp_str, ins2str(ins))
      else:
        debug(csp_str, '0x%X' % ins.u16)

    csp.u16 += 2

  debug('CSB: 0x%X, size: 0x%X' % (csb.u16, len(cs)))
  debug('DSB: 0x%X, size: 0x%X' % (dsb.u16, len(ds)))

  info('Bytecode translation completed')

  return (
    (csb, cs),
    (dsb, ds),
    symbols
  )
