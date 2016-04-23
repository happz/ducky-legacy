try:
  import cPickle as pickle

except ImportError:
  import pickle

import collections
import optparse
import sys

from six import itervalues

def read_profiling_data(logger, files_in):
  from ..profiler import ProfileRecord

  data = collections.defaultdict(ProfileRecord)

  for path in files_in:
    logger.info('Reading profile data from %s', path)

    with open(path, 'rb') as f_in:
      file_data = pickle.load(f_in)

    for record in itervalues(file_data):
      data[record.ip].merge(record)

    logger.debug('%d records merged', len(file_data))

  return data

def main():
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  parser.add_option('-i', dest = 'files_in', action = 'append', default = [], help = 'Input file')
  parser.add_option('-b', dest = 'binary', action = 'store', default = None, help = 'Profiled binary')

  options, logger = parse_options(parser)

  if not options.files_in:
    parser.print_help()
    sys.exit(1)

  if not options.binary:
    parser.print_help()
    sys.exit(1)

  merged_data = read_profiling_data(logger, options.files_in)

  from ..mm.binary import File
  from ..util import SymbolTable

  binary = File.open(logger, options.binary, 'r')
  binary.load()
  binary.load_symbols()

  symbol_table = SymbolTable(binary)

  all_hits = sum([record.count for record in itervalues(merged_data)])

  def print_points():
    from ..mm import UINT32_FMT
    from ..cpu.instructions import DuckyInstructionSet

    table = [
      ['Address', 'Symbol', 'Offset', 'Hits', 'Percentage', 'Inst']
    ]

    for ip in sorted(merged_data.keys(), key = lambda x: merged_data[x].count, reverse = True):
      record = merged_data[ip]
      #binary_ip = record.ip - DEFAULT_BOOTLOADER_ADDRESS
      binary_ip  = record.ip

      symbol, offset = symbol_table[binary_ip]

      if symbol is None:
        symbol_name = ''
        inst_disassembly = '<unknown>'

      else:
        symbol_name = symbol

        symbol = symbol_table.get_symbol(symbol)
        header, content = binary.get_section(symbol.section)

        inst_encoding, inst_cls, inst_opcode = DuckyInstructionSet.decode_instruction(logger, content[(symbol.address + offset - header.base) / 4].value)
        inst_disassembly = DuckyInstructionSet.disassemble_instruction(logger, inst_encoding)

      table.append([UINT32_FMT(binary_ip), symbol_name, UINT32_FMT(offset), record.count, '%.02f' % (float(record.count) / float(all_hits) * 100.0), inst_disassembly])

    logger.table(table)

  print_points()
