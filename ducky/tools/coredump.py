import sys
import optparse
import string

from six import print_

from ..snapshot import CoreDumpFile
from ..mm import PAGE_SIZE, UINT32_FMT
from ..mm.binary import File, SectionTypes
from ..cpu import CoreFlags
from ..cpu.registers import Registers
from ..log import WHITE, GREEN

def show_header(logger, state):
  state = state.get_child('machine')

  logger.info('=== Coredump header ===')
  logger.info('  # of CPUs:      %i', state.nr_cpus)
  logger.info('  # of CPU cores: %i', state.nr_cores)
  logger.info('')

def show_cores(logger, state):
  logger.info('=== Cores ===')

  def __reg(index):
    return UINT32_FMT(cs.registers[index])

  for cpu_state in state.get_child('machine').get_cpu_states():
    for cs in cpu_state.get_core_states():
      logger.info('Core #%i:#%i', cs.cpuid, cs.coreid)

      for i in range(0, Registers.REGISTER_SPECIAL, 4):
        regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
        s = ['reg%02i=%s' % (reg, __reg(reg)) for reg in regs]
        logger.info('  %s', ' '.join(s))

      flags = CoreFlags.from_int(cs.flags)

      logger.info('  fp=%s    sp=%s    ip=%s', __reg(Registers.FP), __reg(Registers.SP), __reg(Registers.IP))
      logger.info('  flags=%s', flags.to_string())
      logger.info('  cnt=%i, alive=%s, running=%s, idle=%s, exit=%i', cs.registers[Registers.CNT], cs.alive, cs.running, cs.idle, cs.exit_code)
      logger.info('  ivt=%s', UINT32_FMT(cs.ivt_address))
      logger.info('  pt= %s, pt-enabled=%s', UINT32_FMT(cs.pt_address), cs.pt_enabled)

      logger.info('')

def show_memory(logger, state):
  logger.info('=== Memory ===')

  state = state.get_child('machine').get_child('memory')

  logger.info('  Size:             %s', state.size)
  logger.info('  # of dirty pages: %s', len(state.get_page_states()))
  logger.info('')

def show_pages(logger, state, empty_pages = False):
  logger.info('=== Memory pages ===')

  for pg in sorted(state.get_child('machine').get_child('memory').get_page_states(), key = lambda x: x.index):
    if not empty_pages and all( i == 0 for i in pg.content):
      continue

    CPR = 32
    pg_addr = pg.index * PAGE_SIZE

    logger.info('  Page #%8i   %s', pg.index, ' '.join(['%02X' % i for i in range(CPR)]))
    # logger.info('    Flags: %s', pg.flags.to_string())

    for i in range(0, 256 // CPR):
      s = []
      t = []

      for b in pg.content[CPR * i:CPR * (i + 1)]:
        c = '%02X' % b
        s.append(GREEN(c) if b == 0 else WHITE(c))

        c = chr(b)
        if c in string.printable[0:-5]:
          c = r'%' if c == '%' else (' ' + c)
          t.append(c)

        elif b == 10:
          t.append(r'\n')

        elif b == 13:
          t.append(r'\r')

        else:
          t.append('  ')

      logger.info('    ' + UINT32_FMT(pg_addr + i * CPR) + ':    ' + ' '.join(s))
      logger.info('                  ' + ' '.join(t))

    logger.info('')

def show_forth_trace(logger, state):
  logger.info('=== FORTH call trace ===')

  bottom = (state.get_child('machine').get_cpu_states()[0].get_core_states()[0].registers[21] & 0xFFFFFF00) / PAGE_SIZE
  top    = 0xFFFFFD
  pages  = [pg for pg in state.get_child('machine').get_child('memory').get_page_states() if bottom <= pg.index < top]

  stack = sorted(pages, key = lambda x: x.index, reverse = True)

  symbols = {}

  with File.open(logger, 'forth/ducky-forth', 'r') as f:
    f.load()

    for i in range(0, f.get_header().sections):
      header, content = f.get_section(i)

      if header.type != SectionTypes.SYMBOLS:
        continue

      for index, entry in enumerate(content):
        symbols[entry.address] = f.string_table.get_string(entry.name)

  for pg in stack:
    for i in range(PAGE_SIZE, 0, -4):
      step = pg.content[i - 4] | (pg.content[i - 3] << 8) | (pg.content[i - 2] << 16) | (pg.content[i - 1] << 24)

      if step in symbols:
        logger.info('%s: %s', UINT32_FMT(step), symbols[step])

      else:
        logger.info(UINT32_FMT(step))

def main():
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  parser.add_option('-i', dest = 'file_in', default = None, help = 'Input file')

  parser.add_option('-H',         dest = 'header',   default = False, action = 'store_true', help = 'Show file header')
  parser.add_option('-C',         dest = 'cores',    default = False, action = 'store_true', help = 'Show cores')
  parser.add_option('-M',         dest = 'memory',   default = False, action = 'store_true', help = 'Show memory')
  parser.add_option('--pages',    dest = 'pages',    default = False, action = 'store_true', help = 'Show pages')
  parser.add_option('--empty-pages', dest = 'empty_pages', default = False, action = 'store_true', help = 'Show empty pages')
  parser.add_option('-F',         dest = 'forth_trace', default = False, action = 'store_true', help = 'Show FORTH call trace')
  parser.add_option('-a',         dest = 'all',      default = False, action = 'store_true', help = 'All of above')

  parser.add_option('-Q',         dest = 'queries',  default = [],    action = 'append',     help = 'Query snapshot')

  options, logger = parse_options(parser)

  if not options.file_in:
    parser.print_help()
    sys.exit(1)

  if options.all:
    options.header = options.cores = options.memory = options.pages = True

  logger.info('Input file: %s', options.file_in)

  with CoreDumpFile.open(logger, options.file_in, 'r') as f_in:
    state = f_in.load()

    if not options.queries:
      logger.info('')

      if options.header:
        show_header(logger, state)

      if options.cores:
        show_cores(logger, state)

      if options.memory:
        show_memory(logger, state)

      if options.pages:
        show_pages(logger, state, empty_pages = options.empty_pages)

      if options.forth_trace:
        show_forth_trace(logger, state)

    else:
      for query in options.queries:
        print_(eval(query, {'STATE': state}), end = '')

if __name__ == '__main__':
  main()
