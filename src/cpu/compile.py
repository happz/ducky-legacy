#!/usr/bin/python

import optparse
import struct
import sys
import types

#import cpu
import irq
import io
#import mm
import cpu.instructions
import mm.binary

from mm import UInt8, UInt16, UINT8_FMT, UINT16_FMT, SEGM_FMT, ADDR_FMT, SIZE_FMT, PAGE_MASK, PAGE_SHIFT, PAGE_SIZE
from cpu.instructions import ins2str
from cpu.errors import CPUException

from util import debug, info

def align_to_next_page(addr):
  return (((addr & PAGE_MASK) >> PAGE_SHIFT) + 1) * PAGE_SIZE

def compile_buffer(buff, csb = None, dsb = None):
  csb = csb or UInt16(0)

  cs_pass1  = []
  ds_pass1 = []

  debug('Pass #1')

  labeled = []

  for line in buff:
    line = line.strip()
    if not line or line[0] == '#':
      continue

    if line.startswith('data'):
      comma_index = line.find(',')
      name = line[5:comma_index]
      value = line[comma_index + 3:-1]

      ds_pass1.append((name, value))
      continue

    # label, instruction, 2nd pass flags
    emited_ins = None

    if line[-1] == ':':
      label = line[0:-1]
      debug('label encountered: "%s"' % label)
      labeled.append(label)
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
      if len(labeled) and i == 0:
        cs_pass1.append((labeled, emited_ins[i]))
        labeled = []
      else:
        cs_pass1.append((None, emited_ins[i]))

    labeled = []

  for name, value in ds_pass1:
    debug('Data entry: "%s"="%s"' % (name, value))

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

  for name, value in ds_pass1:
    references['&' + name] = UInt16(dsp.u16)
    symbols.append(('&' + name, dsp.u16, UInt16(len(value)).u16))

    debug('%s: data entry "%s", size %s' % (ADDR_FMT(dsp.u16), name, SIZE_FMT(len(value))))

    for i in range(0, len(value)):
      ds_pass2.append(UInt8(ord(value[i])))
      dsp.u16 += 1

  for labeled, ins in cs_pass1:
    csp_str = ADDR_FMT(csp.u16)

    if labeled:
      for label in labeled:
        references[label] = UInt16(csp.u16)
        debug(csp_str, 'label entry "%s" created' % label)

    if type(ins) == types.StringType:
      if ins in references:
        cs_pass2.append(references[ins])
        debug(csp_str, 'reference "%s" replaced with %s' % (ins, ADDR_FMT(references[ins].u16)))
      else:
        pass3_required = True
        cs_pass2.append(ins)
        debug(csp_str, 'reference "%s" unknown, fix in the next pass' % ins)
    else:
      cs_pass2.append(ins)

      if type(ins) == cpu.instructions.InstructionBinaryFormat:
        debug(csp_str, ins2str(ins))
      else:
        debug(csp_str, UINT16_FMT(ins.u16))

    csp.u16 += 2

  if pass3_required:
    debug('Pass #3')

    cs_pass3 = []

    for ins in cs_pass2:
      if type(ins) != types.StringType:
        cs_pass3.append(ins)
        continue

      cs_pass3.append(references[ins])
      debug(csp_str, 'reference "%s" replaced with %s' % (ins, ADDR_FMT(references[ins].u16)))

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
