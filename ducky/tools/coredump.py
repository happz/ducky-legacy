import sys
import optparse
import string

from six import itervalues

from ..snapshot import CoreDumpFile
from ..mm import ADDR_FMT, UINT16_FMT, UINT8_FMT, PAGE_SIZE, segment_addr_to_addr, addr_to_segment
from ..mm.binary import SectionFlags, File, SectionTypes
from ..cpu.registers import FlagsRegister, Registers
from ..log import WHITE, GREEN

def show_header(logger, state):
  state = state.get_child('machine')

  logger.info('=== Coredump header ===')
  logger.info('  # of CPUs:      %i', state.nr_cpus)
  logger.info('  # of CPU cores: %i', state.nr_cores)
  logger.info('  # of binaries:  %i', len(state.get_binary_states()))
  logger.info('')

def show_binaries(logger, state):
  logger.info('=== Binaries ===')

  for bs in state.get_child('machine').get_binary_states():
    logger.info('Path: %s', bs.path)
    logger.info('CS: %s DS: %s', UINT8_FMT(bs.cs), UINT8_FMT(bs.ds))
    logger.info('')

    table = [
      ['Section', 'Address', 'Size', 'Flags', 'First page', 'Last page']
    ]

    for rs in itervalues(bs.get_children()):
      flags = SectionFlags.from_uint16(rs.flags)

      table.append([rs.name, ADDR_FMT(rs.address), rs.size, flags.to_string(), rs.pages_start, rs.pages_start + rs.pages_cnt - 1])

    logger.table(table)
    logger.info('')

def show_cores(logger, state):
  logger.info('=== Cores ===')

  def __reg(index):
    return UINT16_FMT(cs.registers[index])

  for cs in state.get_child('machine').get_core_states():
    logger.info('Core #%i:#%i', cs.cpuid, cs.coreid)

    for i in range(0, Registers.REGISTER_SPECIAL, 4):
      regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
      s = ['reg%02i=%s' % (reg, __reg(reg)) for reg in regs]
      logger.info('  %s', ' '.join(s))

    flags = FlagsRegister.from_uint16(cs.registers[Registers.FLAGS])

    logger.info('  cs=%s    ds=%s', __reg(Registers.CS), __reg(Registers.DS))
    logger.info('  fp=%s    sp=%s    ip=%s', __reg(Registers.FP), __reg(Registers.SP), __reg(Registers.IP))
    logger.info('  flags=%s', flags.to_string())
    logger.info('  cnt=%i, alive=%s, running=%s, idle=%s, exit=%i', cs.registers[Registers.CNT], cs.alive, cs.running, cs.idle, cs.exit_code)

    logger.info('')

def show_memory(logger, state):
  logger.info('=== Memory ===')

  state = state.get_child('machine').get_child('memory')

  logger.info('  Size:          %s', state.size)
  logger.info('  # of segments: %s', len(state.segments))
  logger.info('  # of pages:    %s', len(state.get_page_states()))
  logger.info('')

def show_stack(logger, state):
  logger.info('=== Stack ===')

  stacks = [pg for pg in state.get_child('machine').get_child('memory').get_page_states() if pg.stack == 1]

  sps = {}
  for cs in state.get_child('machine').get_core_states():
    sps[segment_addr_to_addr(cs.registers[Registers.DS], cs.registers[Registers.SP])] = '#%i:#%i' % (cs.cpuid, cs.coreid)

  for pg in stacks:
    pg_address = pg.index * PAGE_SIZE
    pg_segment = addr_to_segment(pg_address)

    logger.info('=== Page %s - %s %s ===', pg.index, UINT8_FMT(pg_segment), ADDR_FMT(pg_address))

    for ri in range(0, 16):
      row = []
      for ci in range(0, 8):
        offset = PAGE_SIZE - 2 - (ci * 16 + ri) * 2
        segment_offset = pg_address + offset

        v = pg.content[offset] | (pg.content[offset + 1] << 8)
        row.append((sps.get(segment_offset, None), v))

      logger.info('  ' + '  '.join(['%s %s' % (' ' if sp is None else '*', WHITE(UINT16_FMT(value)) if value != 0 else GREEN(UINT16_FMT(value))) for sp, value in row]))

    logger.info('')

def show_segments(logger, state):
  logger.info('=== Memory segments ===')

  for s in state.get_child('machine').get_child('memory').segments:
    logger.info('  Segment: %s', UINT8_FMT(s))

    for bs in state.get_child('machine').get_binary_states():
      if s == bs.cs:
        logger.info('    CS of %s', bs.path)
      if s == bs.ds:
        logger.info('    DS of %s', bs.path)

  logger.info('')

def show_pages(logger, state):
  logger.info('=== Memory pages ===')

  for pg in sorted(state.get_child('machine').get_child('memory').get_page_states(), key = lambda x: x.index):
    pg_addr = pg.index * PAGE_SIZE
    pg_segment = addr_to_segment(pg_addr)

    for bs in state.get_child('machine').get_binary_states():
      if pg_segment == bs.cs:
        break
      if pg_segment == bs.ds:
        break

    logger.info('  Page #%i (segment %s)', pg.index, UINT8_FMT(pg_segment))
    logger.info('    Flags: %s%s%s%s%s', 'r' if pg.read == 1 else '-', 'w' if pg.write == 1 else '-', 'x' if pg.execute == 1 else '-', 'd' if pg.dirty == 1 else '-', 'c' if pg.cache == 1 else '-')

    CPR = 32

    for i in range(0, 256 / CPR):
      s = []
      t = []

      for b in pg.content[CPR * i:CPR * (i + 1)]:
        c = '%02X' % b
        s.append(GREEN(c) if b == 0 else WHITE(c))

        c = chr(b)
        if c in string.printable[0:-5]:
          c = '%%' if c == '%' else (' ' + c)
          t.append(c)

        elif b == 10:
          t.append('\\n')

        elif b == 13:
          t.append('\\r')

        else:
          t.append('  ')

      logger.info('    ' + ADDR_FMT(pg_addr + i * CPR) + ': ' + ' '.join(s))
      logger.info('              ' + ' '.join(t))

      row_symbols = []
      for j in range(pg_addr + i * CPR, pg_addr + i * CPR + CPR):
        if j not in bs.symbols:
          continue

        row_symbols.append((j - (pg_addr + i * CPR)) * 3 * ' ' + '^' + ', '.join(bs.symbols[j]))

      for symbol in row_symbols:
        logger.info('              ' + symbol)

    logger.info('')

def load_binary_symbols(logger, vs, bs):
  bs.raw_binary = File.open(logger, bs.path, 'r')
  bs.raw_binary.load()

  bs.symbols = {}
  for i in range(0, bs.raw_binary.get_header().sections):
    s_header, s_content = bs.raw_binary.get_section(i)

    if s_header.type != SectionTypes.SYMBOLS:
      continue

    for entry in s_content:
      _header, _content = bs.raw_binary.get_section(entry.section)

      segment = bs.cs if _header.type == SectionTypes.TEXT else bs.ds

      symbol_name = bs.raw_binary.string_table.get_string(entry.name)
      symbol_address = segment_addr_to_addr(segment, entry.address)

      if symbol_address not in bs.symbols:
        bs.symbols[symbol_address] = []
      bs.symbols[symbol_address].append(symbol_name)

def main():
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  parser.add_option('-i', dest = 'file_in', default = None, help = 'Input file')

  parser.add_option('-H',         dest = 'header',   default = False, action = 'store_true', help = 'Show file header')
  parser.add_option('-C',         dest = 'cores',    default = False, action = 'store_true', help = 'Show cores')
  parser.add_option('-M',         dest = 'memory',   default = False, action = 'store_true', help = 'Show memory')
  parser.add_option('--segments', dest = 'segments', default = False, action = 'store_true', help = 'Show segments')
  parser.add_option('--pages',    dest = 'pages',    default = False, action = 'store_true', help = 'Show pages')
  parser.add_option('-b',         dest = 'binaries', default = False, action = 'store_true', help = 'Show binaries')
  parser.add_option('-s',         dest = 'stack',    default = False, action = 'store_true', help = 'Show stack content')
  parser.add_option('-a',         dest = 'all',      default = False, action = 'store_true', help = 'All of above')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if options.all:
    options.header = options.cores = options.memory = options.segments = options.pages = options.binaries = options.stack = True

  logger.info('Input file: %s', options.file_in)

  with CoreDumpFile.open(logger, options.file_in, 'r') as f_in:
    state = f_in.load()

    for bs in state.get_child('machine').get_binary_states():
      load_binary_symbols(logger, state, bs)

    logger.info('')

    if options.header:
      show_header(logger, state)

    if options.binaries:
      show_binaries(logger, state)

    if options.cores:
      show_cores(logger, state)

    if options.memory:
      show_memory(logger, state)

    if options.segments:
      show_segments(logger, state)

    if options.stack:
      show_stack(logger, state)

    if options.pages:
      show_pages(logger, state)

if __name__ == '__main__':
  main()
