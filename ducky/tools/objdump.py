import sys
import optparse
import re
import tabulate

from six import viewkeys, itervalues
from collections import defaultdict

from . import add_common_options, parse_options
from ..cpu.instructions import DuckyInstructionSet, get_instruction_set
from ..mm import UINT16_FMT, SIZE_FMT, UINT32_FMT, UINT8_FMT, WORD_SIZE
from ..mm.binary import File, SectionTypes, SECTION_TYPES, SYMBOL_DATA_TYPES, SymbolDataTypes, RelocFlags, SymbolFlags, SectionFlags
from ..log import get_logger

from ..cpu.coprocessor.math_copro import MathCoprocessorInstructionSet  # noqa

def show_file_header(f):
  f_header = f.header

  I = get_logger().info

  I('=== File header ===')
  I('  Magic:    0x%X', f_header.magic)
  I('  Version:  %i', f_header.version)
  I('  Sections: %i', f_header.sections)
  I('')

def show_sections(options, f):
  I = get_logger().info

  I('=== Sections ===')
  I('')

  table = [
    ['Index', 'Name', 'Type', 'Flags', 'Base', 'Data size', 'Data range', 'File offset', 'File size', 'File range']
  ]

  sections = sorted(list(f.sections), key = lambda x: getattr(x.header, options.sort_sections))

  for section in sections:
    header = section.header
    flags = SectionFlags.from_encoding(header.flags)

    table.append([
      header.index,
      f.string_table.get_string(header.name),
      SECTION_TYPES[header.type],
      '%s (%s)' % (flags.to_string(), UINT16_FMT(flags.to_int())),
      UINT32_FMT(header.base),
      UINT32_FMT(header.data_size),
      '%s - %s' % (UINT32_FMT(header.base), UINT32_FMT(header.base + header.data_size)),
      SIZE_FMT(header.offset),
      SIZE_FMT(header.file_size),
      '%s - %s' % (SIZE_FMT(header.offset), SIZE_FMT(header.offset + header.file_size)),
    ])

  get_logger().table(table)

  I('')

def show_disassemble(f):
  I = get_logger().info

  I('=== Disassemble ==')
  I('')

  instruction_set = DuckyInstructionSet

  symbols = defaultdict(list)

  for section in f.sections:
    if section.header.type != SectionTypes.SYMBOLS:
      continue

    for entry in section.payload:
      symbol_section = f.get_section_by_index(entry.section)

      if symbol_section.header.type != SectionTypes.PROGBITS:
        continue

      if symbol_section.header.flags.executable != 1:
        continue

      symbols[symbol_section.name].append((entry.address, f.string_table.get_string(entry.name)))

  for symbols_list in itervalues(symbols):
    symbols_list.sort(key = lambda x: x[0])

  for section in f.sections:
    if section.header.type != SectionTypes.PROGBITS:
      continue

    if section.header.flags.executable != 1:
      continue

    I('  Section %s', section.name)

    table = [
      ['', '', '', '']
    ]

    symbols_list = symbols[section.name]

    csp = section.header.base

    for i in range(0, len(section.payload), WORD_SIZE):
      raw_inst = section.payload[i] | (section.payload[i + 1] << 8) | (section.payload[i + 2] << 16) | (section.payload[i + 3] << 24)

      prev_symbol_name = symbols_list[0][1]
      for symbol_addr, symbol_name in symbols_list:
        if csp == symbol_addr:
          prev_symbol_name = symbol_name
          break

        if csp < symbol_addr:
          break

        prev_symbol_name = symbol_name

      inst, desc, opcode = instruction_set.decode_instruction(get_logger(), raw_inst)

      table.append([UINT32_FMT(csp), UINT32_FMT(raw_inst), instruction_set.disassemble_instruction(get_logger(), raw_inst), prev_symbol_name])

      if opcode == DuckyInstructionSet.opcodes.SIS:
        instruction_set = get_instruction_set(inst.immediate)

      csp += 4

    get_logger().table(table)
    I('')

def show_reloc(f):
  I = get_logger().info

  I('=== Reloc entries ===')
  I('')

  table = [
    ['Name', 'Flags', 'Patch section', 'Patch address', 'Patch offset', 'Patch size']
  ]

  for section in f.sections:
    if section.header.type != SectionTypes.RELOC:
      continue

    for entry in section.payload:
      patch_section = f.get_section_by_index(entry.patch_section)

      table.append([
        f.string_table.get_string(entry.name),
        RelocFlags.from_encoding(entry.flags).to_string(),
        patch_section.name,
        UINT32_FMT(entry.patch_address),
        entry.patch_offset,
        entry.patch_size
      ])

  get_logger().table(table)
  I('')

def show_symbols(options, f):
  I = get_logger().info

  ascii_replacements = {
    '\n':   '\\n',
    '\r':   '\\r',
    '\x00': '\\0'
  }

  def ascii_replacer(m):
    return ascii_replacements[m.group(0)]

  ascii_replace = re.compile(r'|'.join(viewkeys(ascii_replacements)))

  I('=== Symbols ===')
  I('')

  table = [
    ['Name', 'Section', 'Flags', 'Address', 'Type', 'Size', 'File', 'Content']
  ]

  symbols = []

  for section in f.sections:
    if section.header.type != SectionTypes.SYMBOLS:
      continue

    for entry in section.payload:
      symbol_section = f.get_section_by_index(entry.section)

      symbols.append((entry, f.string_table.get_string(entry.name), symbol_section))

  sort_key = lambda x: x[1]
  if options.sort_symbols == 'address':
    sort_key = lambda x: x[0].address

  symbols = sorted(symbols, key = sort_key)

  for entry, name, section in symbols:
    table_row = [
      name,
      section.name,
      SymbolFlags.from_encoding(entry.flags).to_string(),
      UINT32_FMT(entry.address),
      '%s (%i)' % (SYMBOL_DATA_TYPES[entry.type], entry.type),
      SIZE_FMT(entry.size),
      '%s:%d' % (f.string_table.get_string(entry.filename), entry.lineno)
    ]

    symbol_content = ''

    if section.header.flags.bss == 1:
      pass

    else:
      if entry.type == SymbolDataTypes.INT:
        def __get(i):
          return section.payload[entry.address - section.header.base + i] << (8 * i)

        symbol_content = UINT32_FMT(__get(0) | __get(1) | __get(2) | __get(3))

      elif entry.type == SymbolDataTypes.SHORT:
        def __get(i):
          return section.payload[entry.address - section.header.base + i] << (8 * i)

        symbol_content = UINT16_FMT(__get(0) | __get(1))

      elif entry.type in (SymbolDataTypes.BYTE, SymbolDataTypes.CHAR):
        symbol_content = UINT8_FMT(section.payload[entry.address - section.header.base])

      elif entry.type == SymbolDataTypes.ASCII:
        symbol_content = ''.join(['%s' % chr(c) for c in section.payload[entry.address - section.header.base:entry.address - section.header.base + entry.size]])

      elif entry.type == SymbolDataTypes.STRING:
        symbol_content = ''.join(['%s' % chr(c) for c in section.payload[entry.address - section.header.base:entry.address - section.header.base + entry.size]])

      if entry.type == SymbolDataTypes.ASCII or entry.type == SymbolDataTypes.STRING:
        if options.full_strings is not True and len(symbol_content) > 20:
          symbol_content = symbol_content[0:17] + '...'

        symbol_content = '"' + ascii_replace.sub(ascii_replacer, symbol_content) + '"'

    table_row.append(symbol_content)
    table.append(table_row)

  for line in tabulate.tabulate(table, headers = 'firstrow', tablefmt = 'simple', numalign = 'right').split('\n'):
    I(line)

  I('')

def main():
  parser = optparse.OptionParser()
  add_common_options(parser)

  parser.add_option('-i', dest = 'file_in', action = 'append', default = [], help = 'File to inspect')

  parser.add_option('-H', dest = 'header',      default = False, action = 'store_true', help = 'Show file header')
  parser.add_option('-D', dest = 'disassemble', default = False, action = 'store_true', help = 'Disassemble TEXT sections')
  parser.add_option('-s', dest = 'symbols',     default = False, action = 'store_true', help = 'List symbols')
  parser.add_option('-r', dest = 'reloc',       default = False, action  ='store_true', help = 'List reloc entries')
  parser.add_option('-S', dest = 'sections',    default = False, action = 'store_true', help = 'List sections')
  parser.add_option('-a', dest = 'all',         default = False, action = 'store_true', help = 'All of above')

  group = optparse.OptionGroup(parser, 'Sorting options')
  parser.add_option_group(group)
  group.add_option('--sort-sections', dest = 'sort_sections', default = 'index', action = 'store', type = 'choice', choices = ['index', 'base'])
  group.add_option('--sort-symbols',  dest = 'sort_symbols',  default = 'name',  action = 'store', type = 'choice', choices = ['name', 'address'])

  group = optparse.OptionGroup(parser, 'Display options')
  parser.add_option_group(group)
  group.add_option('--full-strings', dest = 'full_strings', default = False, action = 'store_true')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if options.all:
    options.header = options.disassemble = options.symbols = options.sections = options.reloc = True

  for file_in in options.file_in:
    logger.info('Input file: %s', file_in)

    with File.open(logger, file_in, 'r') as f_in:
      logger.info('')

      if options.header:
        show_file_header(f_in)

      if options.sections:
        show_sections(options, f_in)

      if options.symbols:
        show_symbols(options, f_in)

      if options.reloc:
        show_reloc(f_in)

      if options.disassemble:
        show_disassemble(f_in)
