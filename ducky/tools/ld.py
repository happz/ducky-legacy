import collections
import sys

from six import iteritems

from ..mm import ADDR_FMT, UInt32, UINT32_FMT, UInt16, UInt8, UINT8_FMT, MalformedBinaryError
from ..mm.binary import File, SectionTypes, SymbolEntry, SECTION_ITEM_SIZE
from ..cpu.assemble import align_to_next_page, align_to_next_mmap, sizeof
from ..util import str2int

def align_nop(n):
  return n

class LinkerInfo(object):
  def __init__(self):
    super(LinkerInfo, self).__init__()

    self.section_offsets = collections.defaultdict(dict)
    self.relocations = collections.defaultdict(list)
    self.symbols = collections.defaultdict(list)
    self.section_bases = collections.defaultdict(dict)

def merge_object_into(logger, info, f_dst, f_src):
  r_header, r_content = f_src.get_section_by_name('.reloc')

  for s_header, s_content in f_src.sections():
    if s_header.type == SectionTypes.RELOC:
      info.relocations[f_src].append((s_header, s_content))
      continue

    elif s_header.type == SectionTypes.SYMBOLS:
      info.symbols[f_src].append((s_header, s_content))
      continue

    elif s_header.type == SectionTypes.STRINGS:
      continue

    s_name = f_src.string_table.get_string(s_header.name)

    logger.debug('Merge section %s into dst file', s_name)

    align = align_to_next_mmap if f_dst.get_header().flags.mmapable == 1 else align_nop

    try:
      d_header, d_content = f_dst.get_section_by_name(s_name)

    except MalformedBinaryError:
      logger.debug('No such section exists in dst file yet, copy')

      info.section_offsets[f_src][s_header.index] = 0
      info.section_bases[f_src][s_header.index] = s_header.base

      d_header = f_dst.create_section()
      d_header.type = s_header.type
      d_header.items = s_header.items
      d_header.data_size = s_header.data_size
      d_header.file_size = align(d_header.data_size)
      d_header.name = f_dst.string_table.put_string(s_name)
      d_header.flags = s_header.flags
      f_dst.set_content(d_header, s_content)
      continue

    if d_header.flags.to_uint16() != s_header.flags.to_uint16():
      logger.error('Source section has different flags set: d_header=%s, s_header=%s, f_src=%s', d_header, s_header, f_src)
      sys.exit(1)

    logger.debug('Merging into an existing section: %s', d_header)

    info.section_offsets[f_src][s_header.index] = d_header.data_size
    info.section_bases[f_src][s_header.index] = s_header.base

    d_header.items += s_header.items
    d_header.data_size += s_header.data_size
    d_header.file_size = align(d_header.data_size)
    d_content += s_content
    f_dst.set_content(d_header, d_content)

  f_dst.save()

def fix_section_bases(logger, info, f_out, required_bases):
  D = logger.debug

  D('Fixing base addresses of sections')

  required_bases = dict([(e.split('=')[0], str2int(e.split('=')[1])) for e in required_bases])

  sections_to_fix = {}

  for s_header, s_content in f_out.sections():
    s_header.base = 0xFFFF

    if s_header.type in (SectionTypes.RELOC, SectionTypes.SYMBOLS, SectionTypes.STRINGS):
      continue

    sections_to_fix[f_out.string_table.get_string(s_header.name)] = s_header

  D('sections to fix: %s', sections_to_fix)

  for s_name, s_base in iteritems(required_bases):
    s_header = sections_to_fix[s_name]

    if s_name not in sections_to_fix:
      continue

    s_header.base = s_base
    del sections_to_fix[s_name]

  D('sections to fix without required bases: %s', sections_to_fix)

  fixed_sections = []
  for s_header, s_content in f_out.sections():
    if s_header.type in (SectionTypes.RELOC, SectionTypes.SYMBOLS, SectionTypes.STRINGS):
      continue
    if s_header.base == 0xFFFF:
      continue

    fixed_sections.append(s_header)

  D('fixed sections: %s', fixed_sections)
  fixed_sections = sorted(fixed_sections, key = lambda x: x.base)
  D('fixed sections, sorted: %s', fixed_sections)

  align = align_to_next_mmap if f_out.get_header().flags.mmapable == 1 else align_to_next_page

  def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))

  for s_name, s_header in iteritems(sections_to_fix):
    base = UInt16(0)

    for i, f_header in enumerate(fixed_sections):
      s_area = (base.u16, align(base.u16 + s_header.data_size))
      f_area = (f_header.base, align(f_header.base + f_header.data_size))
      D('s_area: from=%s to=%s' % (ADDR_FMT(s_area[0]), ADDR_FMT(s_area[1])))
      D('f_area: from=%s to=%s' % (ADDR_FMT(f_area[0]), ADDR_FMT(f_area[1])))

      if overlap(s_area, f_area) != 0:
        base.u16 = f_area[1]
        D('  colides with f_area')
        continue

      if i < len(fixed_sections) - 1:
        f_next = fixed_sections[i + 1]
        if s_area[1] > f_next.base:
          base.u16 = f_next[1]
          D('   can not fit between f_header and f_next')
          continue

      D('  fits in')
      s_header.base = base.u16
      fixed_sections.append(s_header)
      fixed_sections = sorted(fixed_sections, key = lambda x: x.base)
      break

    else:
      if fixed_sections:
        base.u16 = align(fixed_sections[-1].base + fixed_sections[-1].data_size)
      else:
        base.u16 = 0

      if base.u16 + s_header.data_size >= 0xFFFF:
        logger.error('Cant fit %s into any space', s_name)
        logger.error('section: %s', s_header)
        logger.error('fixed: %s', fixed_sections)
        sys.exit(1)

      D('  append at the end')
      s_header.base = base.u16
      fixed_sections.append(s_header)
      fixed_sections = sorted(fixed_sections, key = lambda x: x.base)

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
        D('Symbol points to source section: %s', o_header)

        o_name = f_in.string_table.get_string(o_header.name)

        d_header, d_content = f_out.get_section_by_name(o_name)
        D('Symbol points to destination section: %s', d_header)

        D('src base: %s, dst base: %s, symbol addr: %s, section dst offset: %s', ADDR_FMT(o_header.base), ADDR_FMT(d_header.base), ADDR_FMT(s_se.address), ADDR_FMT(info.section_offsets[f_in][o_header.index]))
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
  h_symtab.base = 0xFFFF

  f_out.set_content(h_symtab, symbols)
  h_symtab.data_size = h_symtab.file_size = len(symbols) * sizeof(SymbolEntry())

  f_out.save()

  info.symbols = symbol_map

def resolve_relocations(logger, info, f_out, f_ins):
  D = logger.debug

  D('Resolve relocations')

  for s_header, s_content in f_out.sections():
    D('name=%s base=%s header=%s', f_out.string_table.get_string(s_header.name), ADDR_FMT(s_header.base), s_header)

  for f_in, reloc_sections in iteritems(info.relocations):
    D('Processing file %s', f_in.name)

    for r_header, r_content in reloc_sections:
      for re in r_content:
        D('Relocation: reloc=%s', re)

        s_name = f_in.string_table.get_string(re.name)

        o_header, o_content = f_in.get_section(re.patch_section)
        D('Reloc points to source section: %s', o_header)

        o_name = f_in.string_table.get_string(o_header.name)

        d_header, d_content = f_out.get_section_by_name(o_name)
        D('Reloc points to destination section: %s', d_header)

        D('patch address: %s, patch offset: %s, patch size: %s, old base: %s, new base: %s', ADDR_FMT(re.patch_address), re.patch_offset, re.patch_size, o_header.base, d_header.base)
        fixed_patch_address = re.patch_address - o_header.base + info.section_offsets[f_in][o_header.index] + d_header.base

        D('fixed patch address: %s', ADDR_FMT(fixed_patch_address))

        D('Search for symbol named "%s"', s_name)

        for name, f_src, se in info.symbols:
          if name != s_name:
            continue

          if f_src != f_in and se.flags.globally_visible == 0:
            continue

          D('  Found: %s', se)
          break

        else:
          logger.error('No such symbol: name=%s', s_name)
          continue

        patch_address = se.address
        if re.flags.relative:
          patch_address -= (fixed_patch_address + 4)

        D('Patching %s:%s:%s with %s', ADDR_FMT(fixed_patch_address), re.patch_offset, re.patch_size, ADDR_FMT(patch_address))

        content_index = (fixed_patch_address - d_header.base) // SECTION_ITEM_SIZE[d_header.type]
        D('  Content index: %i (%s - %s) / %s', content_index, fixed_patch_address, d_header.base, SECTION_ITEM_SIZE[d_header.type])

        orig_val = d_content[content_index]

        if isinstance(orig_val, UInt8):
          if re.patch_offset != 0 or re.patch_size != 16:
            logger.warn('Unhandled reloc entry: %s', re)
            sys.exit(1)

          bl = orig_val
          bh = d_content[content_index + 1]

          patch = UInt16(patch_address)
          new_bl = UInt8(patch.u16 & 0x00FF)
          new_bh = UInt8((patch.u16 & 0xFF00) >> 8)

          D('  patched! %s %s => %s %s', UINT8_FMT(bl), UINT8_FMT(bh), UINT8_FMT(new_bl), UINT8_FMT(new_bh))

          bl.u8 = new_bl.u8
          bh.u8 = new_bh.u8

        elif isinstance(orig_val, UInt32):
          new_val = None

          lower_mask = UInt32(0xFFFFFFFF >> (32 - re.patch_offset))
          upper_mask = UInt32(0xFFFFFFFF << (re.patch_offset + re.patch_size))
          mask = UInt32(upper_mask.u32 | lower_mask.u32)
          D('lower mask: %s', UINT32_FMT(lower_mask))
          D('upper mask: %s', UINT32_FMT(upper_mask))
          D('mask: %s', UINT32_FMT(mask))

          D('orig val: %s', UINT32_FMT(orig_val))

          masked = UInt32(orig_val.u32 & mask.u32)

          D('masked: %s', UINT32_FMT(masked.u32))

          patch = UInt32(patch_address << re.patch_offset)
          patch.u32 &= (~mask.u32)
          D('patch: %s', UINT32_FMT(patch))

          new_val = UInt32(masked.u32 | patch.u32)
          D('new val: %s', UINT32_FMT(new_val))

          if orig_val.u32 != new_val.u32:
            D('  patched! %s => %s', UINT32_FMT(orig_val), UINT32_FMT(new_val))

          orig_val.u32 = new_val.u32

        else:
          logger.warn('Unhandled content type: %s', orig_val)
          sys.exit(1)

  f_out.save()

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
  group.add_option('--section-base', dest = 'section_base', action = 'append', default = [], help = 'Set base of section to specific address', metavar = 'SECTION=ADDRESS')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if not options.file_out:
    parser.print_help()
    sys.exit(1)

  if any([not file_in.endswith('.o') for file_in in options.file_in]):
    logger.error('All input files must be object files')
    sys.exit(1)

  files_in = []
  for file_in in options.file_in:
    with File.open(logger, file_in, 'r') as f_in:
      f_in.load()
      files_in.append(f_in)

  if not all([f.get_header().flags.mmapable == files_in[0].get_header().flags.mmapable for f in files_in]):
    logger.error('All input files must have the same mmapable setting')
    sys.exit(1)

  info = LinkerInfo()

  with File.open(logger, options.file_out, 'w') as f_out:
    h_file = f_out.create_header()
    h_file.flags.mmapable = files_in[0].get_header().flags.mmapable

    h_section = f_out.create_section()
    h_section.type = SectionTypes.STRINGS
    h_section.name = f_out.string_table.put_string('.strings')

    for f_in in files_in:
      merge_object_into(logger, info, f_out, f_in)

    fix_section_bases(logger, info, f_out, options.section_base)
    resolve_symbols(logger, info, f_out, files_in)
    resolve_relocations(logger, info, f_out, files_in)

    f_out.save()
