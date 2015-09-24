#! /usr/bin/env python

import os
import sys

if os.environ.get('DUCKY_IMPORT_DEVEL', 'no') == 'yes':
  sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
  import cPickle as pickle

except ImportError:
  import pickle

import collections
import optparse

import ducky.patch
import ducky.log
import ducky.cpu
import ducky.cpu.instructions
import ducky.mm.binary
import ducky.util

from ducky.mm import ADDR_FMT

def main():
  parser = optparse.OptionParser()

  ducky.util.add_common_options(parser)

  parser.add_option('-i', dest = 'files_in', action = 'append', default = [], help = 'Input file')
  parser.add_option('-b', dest = 'binary', action = 'store', default = None, help = 'Profiled binary')

  group = optparse.OptionGroup(parser, 'Output options')
  parser.add_option_group(group)
  group.add_option('-n', '--num-entries', dest = 'num_entries', action = 'store', type = int, default = 20, metavar = 'N', help = 'Display N entries in any listing')

  options, logger = ducky.util.parse_options(parser)

  if not options.files_in:
    parser.print_help()
    sys.exit(1)

  if not options.binary:
    parser.print_help()
    sys.exit(1)

  data = collections.defaultdict(int)

  for path in options.files_in:
    logger.info('Reading profile data from %s', path)

    with open(path, 'rb') as f:
      d = pickle.load(f)

      for k, v in d.iteritems():
        data[k] += v

  all_hits = sum(data.itervalues())

  binary = ducky.mm.binary.File(logger, options.binary, 'r')
  binary.load()
  binary.load_symbols()

  symbol_table = ducky.util.SymbolTable(binary)

  def print_points(addresses):
    table = [
      ['Address', 'Symbol', 'Hits', 'Percentage', 'Inst']
    ]

    for addr in addresses:
      hits = data[addr]
      symbol, offset = symbol_table[addr]

      symbol_name = symbol + (('[%s]' % offset) if offset is not None else '')

      symbol = symbol_table.get_symbol(symbol)
      header, content = binary.get_section(symbol.section)

      table.append([ADDR_FMT(addr), symbol_name, hits, '%.02f' % (float(hits) / float(all_hits) * 100.0), ducky.cpu.instructions.DuckyInstructionSet.decode_instruction(content[(symbol.address + offset - header.base) / 4])])

    logger.table(table)

  def print_symbol_hits(functions):
    table = [
      ['Symbol', 'Hits', 'Percentage']
    ]

    for fn in functions:
      hits = symbol_hits[fn]
      table.append([fn, hits, '%.02f' % (float(hits) / float(all_hits) * 100.0)])

    logger.table(table)

  symbol_hits = collections.defaultdict(int)

  for addr, hits in data.iteritems():
    hits = data[addr]
    symbol, offset = symbol_table[addr]

    symbol_hits[symbol] += hits

  logger.info('')

  keys = sorted(data.keys(), key = data.get, reverse = True)
  print_points(keys[0:options.num_entries])

  logger.info('')

  keys = sorted(symbol_hits.keys(), key = symbol_hits.get, reverse = True)
  print_symbol_hits(keys[0:options.num_entries])

if __name__ == '__main__':
  main()
