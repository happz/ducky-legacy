import ast
import collections
import logging
import os
import re
import sys
import tarfile
import tempfile

from six import iteritems, integer_types
from functools import partial
from collections import defaultdict

from ..mm import i32_t, UINT32_FMT, MalformedBinaryError, WORD_SIZE
from ..mm.binary import File, SectionTypes, SymbolEntry, SectionFlags, SymbolFlags
from ..asm import align_to_next_page
from ..errors import Error, UnalignedJumpTargetError, EncodingLargeValueError, UnknownSymbolError, PatchTooLargeError, BadLinkerScriptError, IncompatibleSectionFlagsError, UnknownDestinationSectionError, LinkerError
from ..log import get_logger

class LinkerScript(object):
  def __init__(self, filepath = None):
    self._filepath = filepath

    self._dst_section_start = collections.OrderedDict()
    self._dst_section_map = collections.OrderedDict()

    if self._filepath is None:
      return

    with open(filepath, 'r') as f:
      data = f.read()

    try:
      script = ast.literal_eval(data)

    except ValueError as e:
      raise BadLinkerScriptError(filepath, e)

    section_start = None

    for entry in script:
      if isinstance(entry, integer_types):
        section_start = entry
        continue

      if not isinstance(entry, tuple):
        continue

      dst_section, src_sections = entry

      if section_start is None:
        self._dst_section_start[dst_section] = None

      else:
        self._dst_section_start[dst_section] = section_start
        section_start = None

      for src_section in src_sections:
        self._dst_section_map[re.compile(r'^' + src_section + r'$')] = dst_section

  def section_ordering(self):
    return self._dst_section_start.keys()

  def where_to_merge(self, src_section):
    for src_section_pattern, dst_section in iteritems(self._dst_section_map):
      if not src_section_pattern.match(src_section):
        continue

      return dst_section

    raise UnknownDestinationSectionError(src_section)

  def where_to_base(self, section):
    return self._dst_section_start.get(section)

class LinkerInfo(object):
  def __init__(self, linker_script):
    super(LinkerInfo, self).__init__()

    self.section_offsets = collections.defaultdict(dict)
    self.relocations = collections.defaultdict(list)
    self.symbols = collections.defaultdict(list)
    self.section_bases = collections.defaultdict(dict)

    self.linker_script = linker_script

def merge_object_into(info, f_dst, f_src):
  D = get_logger().debug

  D('----- * ----- * ----- * ----- * -----')
  D('Merging %s file', f_src.name)
  D('----- * ----- * ----- * ----- * -----')

  for src_section in f_src.sections:
    src_header = src_section.header

    if src_header.type == SectionTypes.RELOC:
      info.relocations[f_src].append(src_section)
      continue

    elif src_header.type == SectionTypes.SYMBOLS:
      src_section._filename = f_src.name
      info.symbols[f_src].append(src_section)
      continue

    elif src_header.type == SectionTypes.STRINGS:
      continue

    assert src_header.type == SectionTypes.PROGBITS

    D('Merge section %s into dst file', src_section.name)

    dst_section_name = info.linker_script.where_to_merge(src_section.name)
    D('  Section "%s" will be merged into "%s"', src_section.name, dst_section_name)

    try:
      dst_section = f_dst.get_section_by_name(dst_section_name, dont_create = True)

    except MalformedBinaryError:
      D('  No such section exists in dst file yet, copy')

      info.section_offsets[f_src][src_header.index] = 0
      info.section_bases[f_src][src_header.index] = src_header.base

      dst_section = f_dst.create_section(name = dst_section_name)
      dst_header = dst_section.header

      dst_header.type      = src_header.type
      dst_header.name      = f_dst.string_table.put_string(dst_section_name)
      dst_header.data_size = src_header.data_size
      dst_header.file_size = src_header.data_size
      dst_header.flags     = src_header.flags
      dst_section.payload  = src_section.payload[:]
      continue

    else:
      dst_header = dst_section.header

    if SectionFlags.from_encoding(dst_header.flags).to_int() != SectionFlags.from_encoding(src_header.flags).to_int():
      raise IncompatibleSectionFlagsError(dst_section, src_section)

    D('  merging into an existing section')
    D('    name=%s, range=%s - %s', dst_section.name, UINT32_FMT(dst_header.base), UINT32_FMT(dst_header.base + dst_header.data_size))
    D('    dst_header=%s', dst_header)

    if dst_header.data_size % WORD_SIZE != 0:
      padding_bytes = WORD_SIZE - (dst_header.data_size % WORD_SIZE)
      D('    * unaligned data section, %d padding bytes appended', padding_bytes)

      dst_header.data_size += padding_bytes
      dst_section.payload += bytearray([0 for _ in range(0, padding_bytes)])

    D('    dst_header=%s', dst_header)

    info.section_offsets[f_src][src_header.index] = dst_header.data_size
    info.section_bases[f_src][src_header.index] = src_header.base

    dst_header.data_size += src_header.data_size
    dst_header.file_size = dst_header.data_size
    dst_section.payload += src_section.payload

def fix_section_bases(info, f_out):
  logger, D = get_logger(), get_logger().debug

  D('----- * ----- * ----- * ----- * -----')
  D('Fixing base addresses of sections')
  D('----- * ----- * ----- * ----- * -----')

  sort_by_base = partial(sorted, key = lambda x: x.header.base)

  D('Sections to fix:')

  sections = {}

  for section in f_out.sections:
    if section.header.type != SectionTypes.PROGBITS:
      continue

    sections[section.name] = section

    base = info.linker_script.where_to_base(section.name)
    section.header.base = base if base is not None else 0xFFFFFFFF

    D('  %s - %s', section.name, section.header)

  tmp_sections = collections.OrderedDict([(section.name, section) for section in sort_by_base(sections.values())])

  for _, section in iteritems(tmp_sections):
    if section.header.base == 0xFFFFFFFF:
      D('  %s floating', section.name)

    else:
      D('  %s @ %s', section.name, UINT32_FMT(section.header.base))

  D('Order: %s', info.linker_script.section_ordering())

  def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))

  sections = []

  D('Looking for section base addresses:')

  def dump_sections():
    D('')
    D('Sections:')

    table = [['Name', 'Start', 'End']]

    for section in sections:
      table.append([name, UINT32_FMT(section.header.base), UINT32_FMT(align_to_next_page(section.header.base + section.header.data_size))])

    logger.table(table, fn = logger.debug)

  for name in info.linker_script.section_ordering():
    dump_sections()

    D('')
    D('Considering %s', name)

    if name not in tmp_sections:
      D('  not present')
      continue

    section = tmp_sections[name]

    D('  section: %s', section)
    D('  header:  %s', section.header)

    if sections:
      last_section = sections[-1]
      base = align_to_next_page(last_section.header.base + last_section.header.data_size)

    else:
      last_section = None
      base = 0x00000000

    D('  suggested base=%s', UINT32_FMT(base))

    if section.header.base == 0xFFFFFFFF:
      D('  base not set')

      if base + section.header.data_size >= 0xFFFFFFFF:
        logger.error('Cannot place %s to a base - no space left', name)
        logger.error('  header: %s', section.header)
        dump_sections()
        sys.exit(1)

      section.header.base = base

    else:
      D('  base requested')

      if section.header.base < base:
        logger.error('Cannot place %s to a requested base - previous section is too long', name)
        logger.error('  header: %s', section.header)
        dump_sections()
        sys.exit(1)

    sections.append(section)
    sections = sort_by_base(sections)

  dump_sections()

def resolve_symbols(info, f_out, f_ins):
  D = get_logger().debug

  D('Resolve symbols - compute their new addresses')

  symbols = []
  symbol_map = []

  symbol_map = defaultdict(list)

  for f_in, symbol_sections in iteritems(info.symbols):
    D('Processing file %s', f_in.name)

    for section in symbol_sections:
      D('Symbol section: %s', section.header)

      for symbol in section.payload:
        symbol_name = f_in.string_table.get_string(symbol.name)
        symbol._filename = f_in.string_table.get_string(symbol.filename)

        D('Symbol: %s', symbol_name)

        src_symbol_section = f_in.get_section_by_index(symbol.section)
        D('  src section: %s', src_symbol_section.header)
        D('  src section name: %s', src_symbol_section.name)

        dst_symbol_section = f_out.get_section_by_name(info.linker_script.where_to_merge(src_symbol_section.name))
        D('  dst section: %s', dst_symbol_section.header)
        D('  dst section name: %s', dst_symbol_section.name)

        D('src base: %s, dst base: %s, symbol addr: %s, section dst offset: %s', UINT32_FMT(src_symbol_section.header.base), UINT32_FMT(dst_symbol_section.header.base), UINT32_FMT(symbol.address), UINT32_FMT(info.section_offsets[f_in][src_symbol_section.header.index]))
        new_addr = symbol.address - src_symbol_section.header.base + info.section_offsets[f_in][src_symbol_section.header.index] + dst_symbol_section.header.base

        dst_symbol = SymbolEntry()
        dst_symbol.flags = symbol.flags
        dst_symbol.name = f_out.string_table.put_string(symbol_name)
        dst_symbol.address = new_addr
        dst_symbol.size = symbol.size
        dst_symbol.section = dst_symbol_section.header.index
        dst_symbol.type = symbol.type
        dst_symbol.filename = f_out.string_table.put_string(symbol._filename)
        dst_symbol.lineno = symbol.lineno

        symbols.append(dst_symbol)
        symbol_map[symbol_name].append((dst_symbol, f_in))

        D('New symbol: %s', dst_symbol)

  symtab = f_out.create_section(name = '.symtab')
  symtab.header.name = f_out.string_table.put_string('.symtab')
  symtab.header.type = SectionTypes.SYMBOLS
  symtab.payload = symbols

  info.symbols = symbol_map


class RelocationPatcher(object):
  def __init__(self, re, se, symbol_name, section, original_section = None, section_offset = 0):
    self._logger = logging.getLogger('ducky')
    self.DEBUG = self._logger.debug

    original_section = original_section or section

    self.DEBUG('%s:', self.__class__.__name__)
    self.DEBUG('  symbol=%s', symbol_name)
    self.DEBUG('  re=%s', re)
    self.DEBUG('  se=%s', se)
    self.DEBUG('  dsection=%s', section.header)
    self.DEBUG('  osection=%s', original_section.header)
    self.DEBUG('  offset=%s', UINT32_FMT(section_offset))

    self._re = re
    self._se = se

    self._patch_section_header = section.header
    self._patch_section_content = section.payload

    self.DEBUG('  section.base=%s, re.address=%s, original.base=%s, section.offset=%s', UINT32_FMT(section.header.base), UINT32_FMT(re.patch_address), UINT32_FMT(original_section.header.base), UINT32_FMT(section_offset))
    self._patch_address = re.patch_address - original_section.header.base + section_offset + section.header.base
    self._patch_address = re.patch_address - section.header.base + (section.header.base - original_section.header.base) + section_offset
    self._ip_address = re.patch_address - original_section.header.base + section.header.base + section_offset
    self.DEBUG('  section.base=%s, patch address=%s, ip=%s', UINT32_FMT(section.header.base), UINT32_FMT(self._patch_address), UINT32_FMT(self._ip_address))

    self._content_index = self._patch_address
    self.DEBUG('  content index=%d', self._content_index)

    self._patch = self._create_patch()
    self.DEBUG('  patch=%s (%s)', UINT32_FMT(self._patch), i32_t(self._patch).value)

  def _create_patch(self):
    patch = self._se.address

    if self._re.flags.relative == 1:
      patch -= (self._ip_address + 4)

    return patch + self._re.patch_add

  def _apply_patch(self, value):
    re = self._re
    se = self._se

    self.DEBUG('  value=%s', UINT32_FMT(value))

    lower_mask = 0xFFFFFFFF >> (32 - re.patch_offset)
    upper_mask = 0xFFFFFFFF << (re.patch_offset + re.patch_size)
    mask = upper_mask | lower_mask

    self.DEBUG('  lmask=%s, umask=%s, mask=%s', UINT32_FMT(lower_mask), UINT32_FMT(upper_mask), UINT32_FMT(mask))

    masked = value & mask
    self.DEBUG('  masked=%s', UINT32_FMT(masked))

    patch = self._patch
    self.DEBUG('  patch:         %s (%s)', UINT32_FMT(patch), patch)

    if re.flags.inst_aligned == 1:
      if patch & 0x3:
        raise UnalignedJumpTargetError(info = 'address=%s' % UINT32_FMT(patch))

      patch = patch // 4

    if patch >= 2 ** re.patch_size:
      raise EncodingLargeValueError(info = 'size=%s, value=%s' % (re.patch_size, UINT32_FMT(patch)))

    self.DEBUG('  patch:         %s (%s)', UINT32_FMT(patch), patch)

    if re.flags.relative == 1:
      lower, upper = -(2 ** (re.patch_size - 1)), (2 ** (re.patch_size - 1)) - 1

    else:
      lower, upper = 0, 2 ** re.patch_size

    self.DEBUG('  patch size:    %s', re.patch_size)
    self.DEBUG('  patch limits:  %s %s', lower, upper)
    self.DEBUG('  patch fits?    %s %s', patch < lower, patch > upper)

    if not (lower <= patch <= upper):
      raise PatchTooLargeError('Patch cannot fit into available space: re={reloc_entry}, se={symbol_entry}, patch={patch}'.format(reloc_entry = re, symbol_entry = se, patch = patch))

    patch = patch << re.patch_offset
    self.DEBUG('  shifted patch: %s', UINT32_FMT(patch))

    patch = patch & (~mask) & 0xFFFFFFFF
    self.DEBUG('  masked patch:  %s', UINT32_FMT(patch))

    value = masked | patch
    self.DEBUG('  patched:       %s', UINT32_FMT(value))

    return value

  def patch(self):
    content = self._patch_section_content
    content_index = self._content_index

    value = content[content_index] | (content[content_index + 1] << 8) | (content[content_index + 2] << 16) | (content[content_index + 3] << 24)
    value = self._apply_patch(value)

    content[content_index] =      value        & 0xFF
    content[content_index + 1] = (value >> 8)  & 0xFF
    content[content_index + 2] = (value >> 16) & 0xFF
    content[content_index + 3] = (value >> 24) & 0xFF

def resolve_relocations(info, f_out, f_ins):
  logger, D = get_logger(), get_logger().debug

  D('')
  D('----- * ----- * ----- * ----- * -----')
  D('Resolve relocations')
  D('----- * ----- * ----- * ----- * -----')

  section_symbols = {}

  for section in f_out.sections:
    D('name=%s base=%s header=%s', section.name, UINT32_FMT(section.header.base), section.header)

    se = SymbolEntry()
    se.flags = SymbolFlags.from_int(0).to_encoding()
    se.name = f_out.string_table.put_string(section.name)
    se.address = section.header.base

    section_symbols[section.name] = se

  for f_in, reloc_sections in iteritems(info.relocations):
    D('Processing file %s', f_in.name)

    for section in reloc_sections:
      for reloc_entry in section.payload:
        D('-----*-----*-----')
        D('  %s', reloc_entry)

        symbol_name = f_in.string_table.get_string(reloc_entry.name)

        # Get all involved sections
        src_section = f_in.get_section_by_index(reloc_entry.patch_section)
        dst_section_name = info.linker_script.where_to_merge(src_section.name)
        dst_section = f_out.get_section_by_name(dst_section_name)

        D('  src section: %s', src_section.name)
        D('  src header: %s', src_section.header)
        D('  dst section: %s', dst_section.name)
        D('  dst header: %s', dst_section.header)
        D('  symbol: %s', symbol_name)
        D('  file: %s', f_in.name)

        # Find referenced symbol
        if symbol_name in info.symbols:
          symbol_family = info.symbols[symbol_name]

          if len(symbol_family) > 1:
            D('  multiple candidates:')
            for se, f_src in symbol_family:
              D('    %s from file %s', se, f_src.name)

            for se, f_src in symbol_family:
              if f_in.name == f_src.name:
                D('  found file match in %s from %s', se, f_in.name)
                break

            else:
              logger.warn('Symbol with name "%s" has multiple candidates but no definitve match', symbol_name)
              logger.warn('  file: %s', f_in.name)

              for se, f_src in symbol_family:
                logger.warn('  %s from file %s', se, f_src.name)

              continue

          else:
            se, f_src = symbol_family[0]

          if f_src != f_in and se.flags.globally_visible == 0:
            raise UnknownSymbolError('Symbol "%s" is not globally visible' % symbol_name)

        else:
          if symbol_name not in section_symbols:
            raise UnknownSymbolError('No such symbol "%s", referenced from %s' % (symbol_name, f_in.name))

          se = section_symbols[symbol_name]

        RelocationPatcher(reloc_entry, se, symbol_name, dst_section, original_section = src_section, section_offset = info.section_offsets[f_in][src_section.header.index]).patch()

def link_files(info, files_in, file_out):
  D = get_logger().debug

  fs_in = []

  cleanup_dirs = []
  opened_files = []

  def __gather_input_files():
    D('----- * ----- * ----- * ----- * -----')
    D('Create a list of input object files')
    D('----- * ----- * ----- * ----- * -----')

    for file_in in files_in:
      D('Input file: %s', file_in)

      if file_in.endswith('.tgz'):
        D('  archive, unpack and add its content')

        with tarfile.open(file_in, 'r:gz') as f_in:
          tmpdir = tempfile.mkdtemp()
          cleanup_dirs.append(tmpdir)

          for member in f_in.getmembers():
            f_in.extract(member, path = tmpdir)

            D('  %s added', os.path.join(tmpdir, member.name))
            fs_in.append(os.path.join(tmpdir, member.name))

      else:
        D('  %s added', file_in)
        fs_in.append(file_in)

    D('')

  try:
    __gather_input_files()

    with File.open(get_logger(), file_out, 'w') as f_out:
      for file_in in fs_in:
        f_in = File.open(get_logger(), file_in, 'r')
        opened_files.append(f_in)

        merge_object_into(info, f_out, f_in)

      fix_section_bases(info, f_out)
      resolve_symbols(info, f_out, fs_in)
      resolve_relocations(info, f_out, fs_in)

      f_out.save()

  except KeyError as e:
    import shutil

    for d in cleanup_dirs:
      shutil.rmtree(d)

    raise e

  finally:
    for f in opened_files:
      f.close()

def archive_files(logger, files_in, file_out):
  D = logger.debug

  D('Merging files into an archive')

  if os.path.exists(file_out):
    D('Unlink existing archive')
    os.unlink(file_out)

  with tarfile.open(file_out, 'w:gz') as f_out:
    for f_in in files_in:
      D('  Adding %s', f_out)
      f_out.add(f_in, recursive = False)

def main():
  import optparse
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  group = optparse.OptionGroup(parser, 'File options')
  parser.add_option_group(group)
  group.add_option('-i', dest = 'file_in', action = 'append', default = [], help = 'Input file')
  group.add_option('-o', dest = 'file_out', default = None, help = 'Output file')
  group.add_option('-f', dest = 'force', default = False, action = 'store_true', help = 'Force overwrite of the output file')

  group = optparse.OptionGroup(parser, 'Linker options')
  parser.add_option_group(group)
  group.add_option('--script',       dest = 'script',       action = 'store',      default = None,  help = 'Linker script')
  group.add_option('--archive',      dest = 'archive',      action = 'store_true', default = False, help = 'Instead of linking, create an archive containing all input files')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if not options.file_out:
    parser.print_help()
    sys.exit(1)

  if any(not file_in.endswith('.o') and not file_in.endswith('.tgz') for file_in in options.file_in):
    logger.error('All input files must be object files')
    sys.exit(1)

  if os.path.exists(options.file_out) and not options.force:
    logger.error('Output file %s already exists, use -f to force overwrite', options.file_out)
    sys.exit(1)

  if options.archive is True:
    archive_files(logger, options.file_in, options.file_out)

  else:
    def __cleanup(exc, msg = None):
      if hasattr(e, 'log'):
        e.log(logger.error)

      else:
        logger.exception(exc)

      if os.path.exists(options.file_out):
        os.unlink(options.file_out)

      sys.exit(1)

    try:
      script = LinkerScript(options.script)
      info = LinkerInfo(script)

      link_files(info, options.file_in, options.file_out)

    except LinkerError as e:
      __cleanup(e)

    except Error as e:
      __cleanup(e)
