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

from ..mm import u8_t, i32_t, u32_t, UINT32_FMT, MalformedBinaryError, WORD_SIZE
from ..mm.binary import File, SectionTypes, SymbolEntry, SECTION_ITEM_SIZE, SectionFlags, SymbolFlags
from ..cpu.assemble import align_to_next_page, align_to_next_mmap, sizeof
from ..cpu.instructions import encoding_to_u32, u32_to_encoding
from ..errors import Error, UnalignedJumpTargetError, EncodingLargeValueError, IncompatibleLinkerFlagsError, UnknownSymbolError, PatchTooLargeError, BadLinkerScriptError

def align_nop(n):
  return n

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

    raise Exception('foo')

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

def merge_object_into(logger, info, f_dst, f_src):
  D = logger.debug

  r_header, r_content = f_src.get_section_by_name('.reloc')

  D('----- * ----- * ----- * ----- * -----')
  D('Merging %s file', f_src.name)
  D('----- * ----- * ----- * ----- * -----')

  for s_header, s_content in f_src.sections():
    if s_header.type == SectionTypes.RELOC:
      info.relocations[f_src].append((s_header, s_content))
      continue

    elif s_header.type == SectionTypes.SYMBOLS:
      info.symbols[f_src].append((s_header, s_content))
      continue

    elif s_header.type == SectionTypes.STRINGS:
      continue

    src_section_name = f_src.string_table.get_string(s_header.name)

    logger.debug('Merge section %s into dst file', src_section_name)

    align = align_to_next_mmap if f_dst.get_header().flags.mmapable == 1 else align_nop

    dst_section_name = info.linker_script.where_to_merge(src_section_name)
    logger.debug('  Section "%s" will be merged into "%s"', src_section_name, dst_section_name)

    try:
      d_header, d_content = f_dst.get_section_by_name(dst_section_name)

    except MalformedBinaryError:
      logger.debug('No such section exists in dst file yet, copy')

      info.section_offsets[f_src][s_header.index] = 0
      info.section_bases[f_src][s_header.index] = s_header.base

      d_header = f_dst.create_section()
      d_header.type = s_header.type
      d_header.items = s_header.items
      d_header.data_size = s_header.data_size
      d_header.file_size = align(d_header.data_size)
      d_header.name = f_dst.string_table.put_string(dst_section_name)
      d_header.flags = s_header.flags
      f_dst.set_content(d_header, s_content)
      continue

    if SectionFlags.from_encoding(d_header.flags).to_int() != SectionFlags.from_encoding(s_header.flags).to_int():
      logger.error('Source section has different flags set: d_header=%s, s_header=%s, f_src=%s', d_header, s_header, f_src)
      sys.exit(1)

    D('  merging into an existing section')
    D('    name=%s, range=%s - %s', dst_section_name, UINT32_FMT(d_header.base), UINT32_FMT(d_header.base + d_header.data_size))
    D('    d_header=%s', d_header)

    if d_header.data_size % WORD_SIZE != 0:
      padding_bytes = WORD_SIZE - (d_header.data_size % WORD_SIZE)
      D('    * unaligned data section, %d padding bytes appended', padding_bytes)

      d_header.data_size += padding_bytes
      for _ in range(0, padding_bytes):
        d_content.append(u8_t(0))

    D('    d_header=%s', d_header)

    info.section_offsets[f_src][s_header.index] = d_header.data_size
    info.section_bases[f_src][s_header.index] = s_header.base

    d_header.items += s_header.items
    d_header.data_size += s_header.data_size
    d_header.file_size = align(d_header.data_size)
    d_content += s_content
    f_dst.set_content(d_header, d_content)

  f_dst.save()

def fix_section_bases(logger, info, f_out):
  D = logger.debug

  D('----- * ----- * ----- * ----- * -----')
  D('Fixing base addresses of sections')
  D('----- * ----- * ----- * ----- * -----')

  sort_by_base = partial(sorted, key = lambda x: x[1].base)

  D('Sections to fix:')

  sections = {}

  for header in f_out.iter_headers():
    if header.type in (SectionTypes.RELOC, SectionTypes.SYMBOLS, SectionTypes.STRINGS):
      continue

    name = f_out.string_table.get_string(header.name)
    sections[name] = header

    base = info.linker_script.where_to_base(name)
    header.base = base if base is not None else 0xFFFFFFFF

    D('  "%s" - %s', name, header)

  tmp_sections = collections.OrderedDict(sort_by_base([(n, h) for n, h in iteritems(sections)]))

  for name, header in iteritems(tmp_sections):
    if header.base == 0xFFFFFFFF:
      D('  %s floating', name)
    else:
      D('  %s @ %s', name, UINT32_FMT(header.base))

  D('Order: %s', info.linker_script.section_ordering())

  align = align_to_next_mmap if f_out.get_header().flags.mmapable == 1 else align_to_next_page

  def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))

  sections = []

  D('Looking for section base addresses:')

  def dump_sections():
    D('')
    D('Sections:')

    table = [['Name', 'Start', 'End']]

    for name, header in sections:
      table.append([name, UINT32_FMT(header.base), UINT32_FMT(align(header.base + header.data_size))])

    logger.table(table, fn = logger.debug)

  for name in info.linker_script.section_ordering():
    dump_sections()

    D('')
    D('Considering %s', name)

    if name not in tmp_sections:
      D('  not present')
      continue

    header = tmp_sections[name]

    if sections:
      last_header = sections[-1][1]
      base = align(last_header.base + last_header.data_size)

    else:
      last_header = None
      base = 0x00000000

    if header.base == 0xFFFFFFFF:
      D('  base not set')

      if base + header.data_size >= 0xFFFFFFFF:
        logger.error('Cannot place %s to a base - no space left', name)
        logger.error('  header: %s', header)
        dump_sections()
        sys.exit(1)

      header.base = base

    else:
      D('  base set')

      if header.base < base:
        logger.error('Cannot place %s to a requested base - previous section is too long', name)
        logger.error('  header: %s', header)
        dump_sections()
        sys.exit(1)

    sections.append((name, header))
    sections = sort_by_base(sections)

  dump_sections()

  f_out.save()

def resolve_symbols(logger, info, f_out, f_ins):
  D = logger.debug

  D('Resolve symbols - compute their new addresses')

  symbols = []
  symbol_map = []

  for f_in, symbol_sections in iteritems(info.symbols):
    D('Processing file %s', f_in.name)

    for s_header, s_content in symbol_sections:
      D('Symbol section: %s', s_header)

      for s_se in s_content:
        s_name = f_in.string_table.get_string(s_se.name)

        D('Symbol: %s', s_name)

        o_header, o_content = f_in.get_section(s_se.section)
        D('  src section: %s', o_header)

        o_src_name = f_in.string_table.get_string(o_header.name)
        D('  src section name: %s', o_src_name)

        o_dst_name = info.linker_script.where_to_merge(o_src_name)
        D('  dst section name: %s', o_dst_name)

        d_header, d_content = f_out.get_section_by_name(o_dst_name)
        D('  dst section: %s', d_header)

        D('src base: %s, dst base: %s, symbol addr: %s, section dst offset: %s', UINT32_FMT(o_header.base), UINT32_FMT(d_header.base), UINT32_FMT(s_se.address), UINT32_FMT(info.section_offsets[f_in][o_header.index]))
        new_addr = s_se.address - o_header.base + info.section_offsets[f_in][o_header.index] + d_header.base

        d_se = SymbolEntry()
        d_se.flags = s_se.flags
        d_se.name = f_out.string_table.put_string(f_in.string_table.get_string(s_se.name))
        d_se.address = new_addr
        d_se.size = s_se.size
        d_se.section = d_header.index
        d_se.type = s_se.type
        d_se.filename = f_out.string_table.put_string(f_in.string_table.get_string(s_se.filename))
        d_se.lineno = s_se.lineno

        symbols.append(d_se)
        symbol_map.append((s_name, f_in, d_se))

        D('New symbol: %s', d_se)

  h_symtab = f_out.create_section()
  h_symtab.type = SectionTypes.SYMBOLS
  h_symtab.items = len(symbols)
  h_symtab.name = f_out.string_table.put_string('.symtab')
  h_symtab.base = 0xFFFFFFFF

  f_out.set_content(h_symtab, symbols)
  h_symtab.data_size = h_symtab.file_size = len(symbols) * sizeof(SymbolEntry())

  f_out.save()

  info.symbols = symbol_map


class RelocationPatcher(object):
  def __init__(self, re, se, symbol_name, section_header, section_content, original_section_header = None, section_offset = 0):
    self._logger = logging.getLogger('ducky')
    self.DEBUG = self._logger.debug

    self.DEBUG('%s:', self.__class__.__name__)
    self.DEBUG('  symbol=%s', symbol_name)
    self.DEBUG('  re=%s', re)
    self.DEBUG('  se=%s', se)
    self.DEBUG('  dsection=%s', section_header)
    self.DEBUG('  osection=%s', original_section_header)
    self.DEBUG('  offset=%s', UINT32_FMT(section_offset))

    self._re = re
    self._se = se

    self._patch_section_header = section_header
    self._patch_section_content = section_content
    original_section_header = original_section_header or section_header

    self.DEBUG('  section.base=%s, re.address=%s, original.base=%s, section.offset=%s', UINT32_FMT(section_header.base), UINT32_FMT(re.patch_address), UINT32_FMT(original_section_header.base), UINT32_FMT(section_offset))
    self._patch_address = re.patch_address - original_section_header.base + section_offset + section_header.base
    self._patch_address = re.patch_address - section_header.base + (section_header.base - original_section_header.base) + section_offset
    self._ip_address = re.patch_address - original_section_header.base + section_header.base + section_offset
    self.DEBUG('  section.base=%s, patch address=%s, ip=%s', UINT32_FMT(section_header.base), UINT32_FMT(self._patch_address), UINT32_FMT(self._ip_address))

    self._content_index = self._patch_address // SECTION_ITEM_SIZE[section_header.type]
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

  def _patch_text(self):
    value = self._patch_section_content[self._content_index]

    if isinstance(value, integer_types):
      value = self._apply_patch(value)

    elif isinstance(value, u32_t):
      value = u32_t(self._apply_patch(value.value))

    else:
      encoded = value
      encoding = type(encoded)
      value = encoding_to_u32(encoded)

      value = self._apply_patch(value)
      value = u32_to_encoding(value, encoding)

    self._patch_section_content[self._content_index] = value

  def _patch_data(self):
    content = self._patch_section_content
    content_index = self._content_index

    value = content[content_index].value | (content[content_index + 1].value << 8) | (content[content_index + 2].value << 16) | (content[content_index + 3].value << 24)
    value = self._apply_patch(value)

    content[content_index].value =      value        & 0xFF
    content[content_index + 1].value = (value >> 8)  & 0xFF
    content[content_index + 2].value = (value >> 16) & 0xFF
    content[content_index + 3].value = (value >> 24) & 0xFF

  def patch(self):
    if self._patch_section_header.type == SectionTypes.TEXT:
      self._patch_text()

    elif self._patch_section_header.type == SectionTypes.DATA:
      self._patch_data()

def resolve_relocations(logger, info, f_out, f_ins):
  D = logger.debug

  D('Resolve relocations')

  section_symbols = {}

  for s_header, s_content in f_out.sections():
    D('name=%s base=%s header=%s', f_out.string_table.get_string(s_header.name), UINT32_FMT(s_header.base), s_header)

    se = SymbolEntry()
    se.flags = SymbolFlags.from_int(0).to_encoding()
    se.name = s_header.name
    se.address = s_header.base

    section_symbols[f_out.string_table.get_string(s_header.name)] = se

  for f_in, reloc_sections in iteritems(info.relocations):
    D('Processing file %s', f_in.name)

    for r_header, r_content in reloc_sections:
      for reloc_entry in r_content:
        D('-----*-----*-----')
        D('  %s', reloc_entry)

        symbol_name = f_in.string_table.get_string(reloc_entry.name)

        # Get all involved sections
        src_header, _ = f_in.get_section(reloc_entry.patch_section)
        src_section_name = f_in.string_table.get_string(src_header.name)
        dst_section_name = info.linker_script.where_to_merge(src_section_name)
        dst_header, dst_content = f_out.get_section_by_name(dst_section_name)

        D('  src section: %s', src_section_name)
        D('  src header: %s', src_header)
        D('  dst section: %s', dst_section_name)
        D('  dst header: %s', dst_header)
        D('  symbol: %s', symbol_name)

        # Find referenced symbol
        for name, f_src, se in info.symbols:
          if name != symbol_name:
            continue

          if f_src != f_in and se.flags.globally_visible == 0:
            continue

          break

        else:
          # Try searching sections
          if symbol_name not in section_symbols:
            raise UnknownSymbolError('No such symbol: name=%s' % symbol_name)

          se = section_symbols[symbol_name]

        RelocationPatcher(reloc_entry, se, symbol_name, dst_header, dst_content, original_section_header = src_header, section_offset = info.section_offsets[f_in][src_header.index]).patch()

  f_out.save()

def link_files(logger, info, files_in, file_out):
  fs_in = []

  def __read_object_file(f):
    with File.open(logger, f, 'r') as f_in:
      f_in.load()
      fs_in.append(f_in)

  for file_in in files_in:
    if file_in.endswith('.tgz'):
      with tarfile.open(file_in, 'r:gz') as f_in:
        tmpdir = None

        try:
          tmpdir = tempfile.mkdtemp()

          for member in f_in.getmembers():
            f_in.extract(member, path = tmpdir)
            __read_object_file(os.path.join(tmpdir, member.name))

        finally:
          if tmpdir is not None:
            import shutil
            shutil.rmtree(tmpdir)

    else:
      __read_object_file(file_in)

  if not all([f.get_header().flags.mmapable == fs_in[0].get_header().flags.mmapable for f in fs_in]):
    raise IncompatibleLinkerFlagsError()

  with File.open(logger, file_out, 'w') as f_out:
    h_file = f_out.create_header()
    h_file.flags.mmapable = fs_in[0].get_header().flags.mmapable

    h_section = f_out.create_section()
    h_section.type = SectionTypes.STRINGS
    h_section.name = f_out.string_table.put_string('.strings')

    for f_in in fs_in:
      merge_object_into(logger, info, f_out, f_in)

    fix_section_bases(logger, info, f_out)
    resolve_symbols(logger, info, f_out, fs_in)
    resolve_relocations(logger, info, f_out, fs_in)

    f_out.save()

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
      if msg is None:
        logger.exception(exc)

      else:
        logger.error(msg)

      if os.path.exists(options.file_out):
        os.unlink(options.file_out)

      sys.exit(1)

    try:
      script = LinkerScript(options.script)
      info = LinkerInfo(script)

      link_files(logger, info, options.file_in, options.file_out)

    except IncompatibleLinkerFlagsError as e:
      __cleanup(e, msg = 'All input files must have the same mmapable setting')

    except BadLinkerScriptError as e:
      __cleanup(e, msg = 'Bad linker script: script={script}, error={error}'.format(script = e.script, error = str(e.exc)))

    except Error as e:
      __cleanup(e)
