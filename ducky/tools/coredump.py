import sys
import optparse
import string

from six import print_, iteritems
from functools import partial

from ..snapshot import CoreDumpFile
from ..mm import PAGE_SIZE, UINT32_FMT, PAGE_MASK, u32_t, u16_t, u8_t, UINT8_FMT, UINT16_FMT
from ..mm.binary import File, SectionTypes
from ..cpu import CoreFlags
from ..cpu.registers import Registers
from ..log import WHITE, GREEN
from ..util import str2int, align

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
    if not empty_pages and all(i == 0 for i in pg.content):
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

def __load_forth_symbols(logger):
  symbols = {}

  with File.open(logger, 'forth/ducky-forth', 'r') as f:
    f.load()

    for i in range(0, f.get_header().sections):
      header, content = f.get_section(i)

      if header.type != SectionTypes.SYMBOLS:
        continue

      for index, entry in enumerate(content):
        symbols[entry.address] = f.string_table.get_string(entry.name)

  return symbols

def __read(state, cnt, address):
  pid = (address & PAGE_MASK) >> 8
  offset = address & 0xFF

  pg = [pg for pg in state.get_child('machine').get_child('memory').get_page_states() if pg.index == pid][0]

  if cnt == 1:
    return u8_t(pg.content[offset])

  if cnt == 2:
    return u16_t(pg.content[offset] | (pg.content[offset + 1] << 8))

  if cnt == 4:
    return u32_t(pg.content[offset] | (pg.content[offset + 1] << 8) | (pg.content[offset + 2] << 16) | (pg.content[offset + 3] << 24))

def __show_forth_word(logger, state, symbols, base_address, ending_addresses):
  __read_u8  = partial(__read, state, 1)
  __read_u16 = partial(__read, state, 2)
  __read_u32 = partial(__read, state, 4)

  namelen = __read_u8(base_address + 7).value

  code_address = align(4, base_address + 8 + namelen)

  logger.info('Base address: %s', UINT32_FMT(base_address))
  logger.info('Link:         %s', UINT32_FMT(__read_u32(base_address)))
  logger.info('CRC:          %s', UINT16_FMT(__read_u16(base_address + 4)))
  logger.info('flags:        %s', UINT8_FMT(__read_u8(base_address + 6)))
  logger.info('namelen:      %s', namelen)
  logger.info('name:         %s', ''.join([chr(__read_u8(base_address + 8 + i).value) for i in range(0, namelen)]))

  while True:
    code_token = __read_u32(code_address).value
    token_name = symbols.get(code_token, '<unknown>')

    logger.info('              %s - %s', UINT32_FMT(code_token), token_name)

    if code_token in ending_addresses:
      break

    if token_name.startswith('code_'):
      break

    code_address += 4

def show_forth_trace(logger, state):
  logger.info('=== FORTH call trace ===')

  bottom = (state.get_child('machine').get_cpu_states()[0].get_core_states()[0].registers[21] & 0xFFFFFF00) / PAGE_SIZE
  top    = 0xFFFFFA
  pages  = [pg for pg in state.get_child('machine').get_child('memory').get_page_states() if bottom <= pg.index < top]

  stack = sorted(pages, key = lambda x: x.index, reverse = True)

  symbols = __load_forth_symbols(logger)

  for pg in stack:
    for i in range(PAGE_SIZE, 0, -4):
      step = pg.content[i - 4] | (pg.content[i - 3] << 8) | (pg.content[i - 2] << 16) | (pg.content[i - 1] << 24)

      if step != 0 and step in symbols:
        logger.info('%s: %s', UINT32_FMT(step), symbols[step])

      else:
        logger.info('%s: %s', UINT32_FMT(step), UINT32_FMT(step))

def show_forth_word(logger, state, base_address):
  logger.info('=== FORTH word ===')

  symbols = __load_forth_symbols(logger)

  __show_forth_word(logger, state, symbols, base_address, [[k for k, v in iteritems(symbols) if v == 'EXIT'][0]])

def show_forth_dict(logger, state, last):
  logger.info('== FORTH dictionary ===')

  __read_u32 = partial(__read, state, 4)

  symbols = __load_forth_symbols(logger)

  base_address = __read_u32(last).value
  ending_addresses = [[k for k, v in iteritems(symbols) if v == 'EXIT'][0]]

  while base_address != 0x00000000:
    logger.info('')
    __show_forth_word(logger, state, symbols, base_address, ending_addresses)
    base_address = __read_u32(base_address).value

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
  parser.add_option('--forth-trace', dest = 'forth_trace', default = False, action = 'store_true', help = 'Show FORTH call trace')
  parser.add_option('--forth-word',  dest = 'forth_word',  default = None,  action = 'store',    help = 'Show FORTH word')
  parser.add_option('--forth-dict',  dest = 'forth_dict',  default = None,  action = 'store',      help = 'Show FORTH dictionary')
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

      if options.forth_word:
        show_forth_word(logger, state, str2int(options.forth_word))

      if options.forth_dict:
        show_forth_dict(logger, state, str2int(options.forth_dict))

    else:
      for query in options.queries:
        print_(eval(query, {'STATE': state}), end = '')

if __name__ == '__main__':
  main()
