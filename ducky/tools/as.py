import os
import sys

from six import iteritems, PY2

def translate_buffer(logger, buffer, file_in, options):
  from ..cpu.assemble import AssemblerError, translate_buffer

  try:
    return translate_buffer(logger, buffer, mmapable_sections = options.mmapable_sections, writable_sections = options.writable_sections, filename = file_in, defines = options.defines, includes = options.includes, verify_disassemble = options.verify_disassemble)

  except AssemblerError as exc:
    exc.log(logger.error)
    sys.exit(1)


def encode_blob(logger, file_in, options):
  logger.debug('encode_blob: file_in=%s', file_in)

  from ..cpu.assemble import DataSection, SymbolsSection, IntSlot, Label, sizeof, BytesSlot, RelocSection, SourceLocation
  from ..mm.binary import SectionFlags

  section_name = '__' + os.path.split(file_in)[1].replace('.', '_').replace('-', '_')
  section = DataSection('.%s' % section_name, flags = SectionFlags.from_string(options.blob_flags.upper()))
  section.base = section.ptr = 0

  symtab = SymbolsSection('.symtab')
  symtab.base = symtab.ptr = 0

  reloc = RelocSection('.reloc')
  reloc.base = reloc.ptr = 0

  if options.mmapable_sections is True:
    section.flags.mmapable = True

  logger.debug('section: %s', section)

  with open(file_in, 'rb') as f_in:
    if PY2:
      data = bytearray([ord(c) for c in f_in.read()])

    else:
      data = f_in.read()

  var_size = IntSlot()
  var_size.name = Label('%s_size' % section_name, section, SourceLocation(filename = file_in, lineno = 0))
  var_size.value = len(data)
  var_size.section = section
  var_size.section_ptr = 0
  var_size.close()

  section.content += var_size.value
  symtab.content.append(var_size)

  var_content = BytesSlot()
  var_content.name = Label('%s_start' % section_name, section, SourceLocation(filename = file_in, lineno = 0))
  var_content.value = data
  var_content.section = section
  var_content.section_ptr = sizeof(var_size)
  var_content.close()

  section.content += var_content.value
  symtab.content.append(var_content)

  logger.debug('section: %s', section)

  return {section.name: section, '.symtab': symtab, '.reloc': reloc}

def save_object_file(logger, sections, file_out, options):
  if os.path.exists(file_out) and not options.force:
    logger.error('Output file %s already exists, use -f to force overwrite', file_out)
    sys.exit(1)

  from ..cpu.assemble import sizeof
  from ..mm.binary import File, SectionTypes, SymbolEntry, RelocEntry

  section_name_to_index = {}

  i = 0
  for s_name, section in list(iteritems(sections)):
    if section.type in (SectionTypes.SYMBOLS, SectionTypes.RELOC):
      continue

    if section.flags.bss and section.data_size > 0:
      continue

    if section.data_size > 0:
      continue

    del sections[s_name]

    section_name_to_index[s_name] = i
    i += 1

  with File.open(logger, file_out, 'w') as f_out:
    h_file = f_out.create_header()
    h_file.flags.mmapable = 1 if options.mmapable_sections else 0

    filenames = {}

    section_name_to_index = {}
    for i, s_name in enumerate(sections.keys()):
      section_name_to_index[s_name] = i

    for s_name, section in iteritems(sections):
      h_section = f_out.create_section()
      h_section.type = section.type
      h_section.items = section.items
      h_section.data_size = section.data_size
      h_section.file_size = section.file_size
      h_section.name = f_out.string_table.put_string(section.name)
      h_section.base = section.base

      if section.type == SectionTypes.SYMBOLS:
        symbol_entries = []

        for se in section.content:
          entry = SymbolEntry()
          symbol_entries.append(entry)

          entry.flags = se.flags.to_encoding()
          entry.name = f_out.string_table.put_string(se.name.name)
          entry.address = se.section_ptr
          entry.size = se.size
          entry.section = section_name_to_index[se.section.name]

          if se.location is not None:
            loc = se.location

            if loc.filename not in filenames:
              filenames[loc.filename] = f_out.string_table.put_string(loc.filename)
            entry.filename = filenames[loc.filename]

            if loc.lineno:
              entry.lineno = loc.lineno

          entry.type = se.symbol_type

        f_out.set_content(h_section, symbol_entries)
        h_section.data_size = h_section.file_size = sizeof(SymbolEntry()) * len(symbol_entries)

      elif section.type == SectionTypes.RELOC:
        reloc_entries = []

        for rs in section.content:
          entry = RelocEntry()
          reloc_entries.append(entry)

          entry.name = f_out.string_table.put_string(rs.name)
          entry.flags = rs.flags.to_encoding()
          entry.patch_section = section_name_to_index[rs.patch_section.name]
          entry.patch_address = rs.patch_address
          entry.patch_offset = rs.patch_offset or 0
          entry.patch_size = rs.patch_size
          entry.patch_add = rs.patch_add or 0

        f_out.set_content(h_section, reloc_entries)
        h_section.data_size = h_section.file_size = sizeof(RelocEntry()) * len(reloc_entries)

      else:
        h_section.flags = section.flags.to_encoding()
        f_out.set_content(h_section, section.content)

    h_section = f_out.create_section()
    h_section.type = SectionTypes.STRINGS
    h_section.name = f_out.string_table.put_string('.strings')

    f_out.save()

def main():
  import optparse
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  group = optparse.OptionGroup(parser, 'File options')
  parser.add_option_group(group)
  group.add_option('-i', dest = 'file_in', action = 'append', default = [], help = 'Input file')
  group.add_option('-o', dest = 'file_out', action = 'append', default = [], help = 'Output file')
  group.add_option('-f', dest = 'force', default = False, action = 'store_true', help = 'Force overwrite of the output file')

  group = optparse.OptionGroup(parser, 'Translation options')
  parser.add_option_group(group)
  group.add_option('-D', dest = 'defines', action = 'append', default = [], help = 'Define variable', metavar = 'VAR')
  group.add_option('-I', dest = 'includes', action = 'append', default = [], help = 'Add directory to list of include dirs', metavar = 'DIR')
  group.add_option('--verify-disassemble', dest = 'verify_disassemble', action = 'store_true', default = False, help = 'Verify that disassebler instructions match input text')

  group = optparse.OptionGroup(parser, 'Binary options')
  parser.add_option_group(group)
  group.add_option('-b', '--blob',              dest = 'blob',              action = 'store_true', default = False, help = 'Create object file wrapping a binary blob')
  group.add_option('-B', '--blob-flags',        dest = 'blob_flags',        action = 'store',      default = 'rl',  help = 'Flags of blob section')
  group.add_option('-m', '--mmapable-sections', dest = 'mmapable_sections', action = 'store_true', default = False, help = 'Create mmap\'able sections')
  group.add_option('-w', '--writable-sections', dest = 'writable_sections', action = 'store_true', default = False, help = '.text and other read-only sections will be marked as writable too')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if len(options.file_out) and len(options.file_out) != len(options.file_in):
    logger.error('If specified, number of output files must be equal to number of input files')
    sys.exit(1)

  for file_in in options.file_in:
    with open(file_in, 'r') as f_in:
      buffer = f_in.read()

    if options.file_out:
      file_out = options.file_out.pop(0)

    else:
      file_out = os.path.splitext(file_in)[0] + '.o'

    if options.blob is True:
      sections = encode_blob(logger, file_in, options)

    else:
      sections = translate_buffer(logger, buffer, file_in, options)

    save_object_file(logger, sections, file_out, options)
