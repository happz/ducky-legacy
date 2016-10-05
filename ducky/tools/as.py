import os
import sys

from six import iteritems, PY2

from ..errors import PatchTooLargeError, AssemblerError
from ..log import get_logger

def get_assembler_process(logger, buffer, file_in, options):
  from ..asm import AssemblerProcess

  return AssemblerProcess(file_in, defines = options.defines, includes = options.includes, logger = logger)

def encode_blob(logger, file_in, options):
  logger = get_logger()

  logger.debug('encode_blob: file_in=%s', file_in)

  from ..mm.binary import SectionTypes
  from ..asm.ast import SourceLocation
  from ..asm import Section, SymbolsSection, IntSlot, Label, BytesSlot, RelocSection

  s_name = '.__' + os.path.split(file_in)[1].replace('.', '_').replace('-', '_')
  section = Section(s_name, s_type = SectionTypes.PROGBITS, s_flags = options.blob_flags.upper())
  section.base = section.ptr = 0

  symtab = SymbolsSection()
  reloc = RelocSection()

  logger.debug('section: %s', section)

  with open(file_in, 'rb') as f_in:
    if PY2:
      data = bytearray([ord(c) for c in f_in.read()])

    else:
      data = f_in.read()

  loc = SourceLocation(filename = file_in, lineno = 0)

  slot_size = IntSlot(None, value = len(data), section = section, section_ptr = 0, location = loc, labels = [Label('%s_size' % s_name, section, loc)])
  slot_size.finalize_value()

  slot_content = BytesSlot(None, value = data, section = section, section_ptr = slot_size.size, location = loc, labels = [Label('%s_start' % s_name, section, loc)])
  slot_content.finalize_value()

  section.content += slot_size.value
  section.content += slot_content.value
  section.content = bytearray(section.content)

  symtab.content.append(slot_size)
  symtab.content.append(slot_content)

  logger.debug('section: %s', section)

  return {s_name: section, '.symtab': symtab, '.reloc': reloc}

def save_object_file(logger, sections, file_out, options):
  logger = get_logger()
  D = logger.debug

  if os.path.exists(file_out) and not options.force:
    logger.error('Output file %s already exists, use -f to force overwrite', file_out)
    sys.exit(1)

  from ..mm.binary import File, SectionTypes, SymbolEntry, SymbolFlags, RelocEntry

  D('* Remove empty and unused sections')

  for name, section in list(iteritems(sections)):
    D('  %s', name)

    if section.type in (SectionTypes.SYMBOLS, SectionTypes.RELOC):
      D('    RELOC or SYMTAB')
      continue

    if section.flags.bss is True and (section.ptr - section.base) > 0:
      D('    BSS with non-zero payload')
      continue

    if section.data_size > 0:
      D('    non-zero data length')
      continue

    D('    removing')
    del sections[name]

  with File.open(logger, file_out, 'w') as f_out:
    D('Create file sections for memory sections')

    def __init_section_entry(section):
      f_section = f_out.get_section_by_name(section.name)

      f_section.header.type = section.type
      f_section.header.name = f_out.string_table.put_string(section.name)

      if section.type == SectionTypes.PROGBITS:
        f_section.header.flags = section.flags.to_encoding()
        f_section.header.base = section.base
        f_section.header.data_size = section.data_size

      return f_section

    for name, section in iteritems(sections):
      f_out.create_section(name = name)

    symbols = {}

    D('Create symbol entries')

    m_section = sections['.symtab']
    f_section = __init_section_entry(m_section)

    symtab_content = []

    D('  %s', m_section)
    D('  %s', f_section.header)

    for slot in m_section.content:
      D('  %s', slot)

      for label in slot.labels:
        D('    %s', label)

        entry = SymbolEntry()

        symbols[label.name] = (slot, entry)
        symtab_content.append(entry)

        entry.type = slot.symbol_type
        entry.flags = SymbolFlags.create(globally_visible = label.globally_visible).to_encoding()
        entry.name = f_out.string_table.put_string(label.name)
        entry.address = slot.section_ptr
        entry.size = slot.size
        entry.section = f_out.get_section_by_name(slot.section.name).header.index

        entry.filename = f_out.string_table.put_string(slot.location.filename)
        entry.lineno = slot.location.lineno

        D('    %s', entry)

    f_section.payload = symtab_content

    D('* Init sections and their payloads')

    for s_name, m_section in iteritems(sections):
      D('  memory section: %s', m_section)

      if m_section.type == SectionTypes.RELOC:
        continue

      f_section = __init_section_entry(m_section)
      D('  file section: %s', f_section.header)

      if m_section.flags.bss is True:
        f_section.payload = []
        f_section.header.file_size = m_section.file_size
        continue

      if m_section.type == SectionTypes.SYMBOLS:
        f_section.payload = symtab_content

      else:
        f_section.payload = m_section.content

    D('')
    D('* Reloc entries')
    D('')

    f_section = __init_section_entry(sections['.reloc'])
    reloc_content = []

    for rs in sections['.reloc'].content:
      re = RelocEntry()

      re.name = f_out.string_table.put_string(rs.name)
      re.flags = rs.flags.to_encoding()
      re.patch_section = f_out.get_section_by_name(rs.patch_section.name).header.index
      re.patch_address = rs.patch_address
      re.patch_offset = rs.patch_offset or 0
      re.patch_size = rs.patch_size
      re.patch_add = rs.patch_add or 0

      D('  %s', re)
      if rs.name not in symbols:
        reloc_content.append(re)
        continue

      slot, se = symbols[rs.name]

      if slot.section.name != rs.patch_section.name:
        reloc_content.append(re)
        continue

      if slot.section.flags.executable is not True:
        reloc_content.append(re)
        continue

      D('    Can resolve this entry')

      from .ld import RelocationPatcher

      try:
        RelocationPatcher(re, se, rs.name, f_out.get_section_by_name(rs.patch_section.name)).patch()

      except PatchTooLargeError as exc:
        exc.log(logger.error)
        sys.exit(1)

    f_section.payload = reloc_content

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
  group.add_option('-E', dest = 'preprocess', action = 'store_true', default = False, help = 'Preprocess only')
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

    if options.preprocess is True:
      process = get_assembler_process(logger, buffer, file_in, options)
      process.preprocess()

      with open(file_out, 'w') as f_out:
        f_out.write(process.preprocessed)

    else:
      if options.blob is True:
        sections = encode_blob(logger, file_in, options)

      else:
        process = get_assembler_process(logger, buffer, file_in, options)

        try:
          process.translate()

        except AssemblerError as e:
          e.log(logger.error)
          sys.exit(1)

        sections = process.sections_pass3

      save_object_file(logger, sections, file_out, options)
