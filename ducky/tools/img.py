import os
import sys

from six.moves import range

from ..mm import u32_t, u8_t, PAGE_SIZE
from ..mm.binary import File, SectionTypes, SectionFlags
from ..util import BinaryFile, align
from ..devices.storage import BLOCK_SIZE
from ..hdt import HDT

NULL8  = u8_t(0)
NULL32 = u32_t(0)

def align_file(logger, f_out, boundary):
  logger.debug('Adding padding bytes to align with BLOCK_SIZE')

  f_out.seek(0, os.SEEK_END)
  pos = f_out.tell()
  logger.debug('  Last position: %s => %s', pos, align(boundary, pos))

  missing = align(boundary, pos) - pos
  logger.debug('  Missing %s bytes', missing)

  for _ in range(0, missing):
    f_out.write(NULL8)

def create_binary_image(logger, f_in, f_out, bio = False):
  f_out.seek(0)

  reserved_space = 0

  if bio is True:
    logger.debug('Reserving 1st block for header')

    reserved_space = BLOCK_SIZE

    for _ in range(0, BLOCK_SIZE // 4):
      f_out.write(NULL32)

  for s_header, s_content in f_in.sections():
    s_name = f_in.string_table.get_string(s_header.name)
    s_flags = SectionFlags.from_encoding(s_header.flags)

    logger.debug('Process section %s', s_name)

    if s_header.type not in (SectionTypes.TEXT, SectionTypes.DATA):
      logger.debug('  Not a text or data section, ignore')
      continue

    if s_flags.loadable != 1:
      logger.debug('  Not loadable, ignore')
      continue

    logger.debug('  Base 0x%08X', s_header.base)
    logger.debug('  Seeking to %s', s_header.base + reserved_space)
    f_out.seek(s_header.base + reserved_space)

    if s_flags.bss == 1:
      for i in range(0, s_header.data_size):
        f_out.write(NULL8)

    else:
      for i, item in enumerate(s_content):
        f_out.write(item)

    logger.debug('%s items written', i)

  align_file(logger, f_out, BLOCK_SIZE if bio else PAGE_SIZE)

  end = f_out.tell()
  logger.debug('Last position: %s', end)

  if bio is True:
    logger.debug('Writing header')

    f_out.seek(0)
    f_out.write(u32_t(end // BLOCK_SIZE))

  f_out.flush()

def create_hdt_image(logger, file_in, f_out, options):
  from .vm import process_config_options

  config = process_config_options(logger,
                                  config_file = file_in,
                                  set_options = [(section,) + tuple(option.split('=')) for section, option in (option.split(':') for option in options.set_options)],
                                  add_options = [(section,) + tuple(option.split('=')) for section, option in (option.split(':') for option in options.add_options)],
                                  enable_devices = options.enable_devices,
                                  disable_devices = options.disable_devices)

  hdt = HDT(logger, config = config)
  hdt.create()

  f_out.seek(0)

  f_out.write(hdt.header)

  for entry in hdt.entries:
    f_out.write(entry)

  align_file(logger, f_out, PAGE_SIZE)

  f_out.flush()

def main():
  import optparse
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  group = optparse.OptionGroup(parser, 'File options')
  parser.add_option_group(group)
  group.add_option('-i', dest = 'file_in', default = None, help = 'Input file')
  group.add_option('-o', dest = 'file_out', default = None, help = 'Output file')
  group.add_option('-f', dest = 'force', default = False, action = 'store_true', help = 'Force overwrite of the output file')

  group = optparse.OptionGroup(parser, 'Image options')
  parser.add_option_group(group)
  group.add_option('-b', '--binary', dest = 'image', action = 'store_const', const = 'binary', help = 'Create image of a binary', default = 'binary')
  group.add_option('-H', '--hdt',    dest = 'image', action = 'store_const', const = 'hdt',    help = 'Create image of HDT')
  group.add_option('--bio',          dest = 'bio',   action = 'store_true',  default = False,  help = 'Allow loading by BIO')

  group = optparse.OptionGroup(parser, 'Machine config options')
  parser.add_option_group(group)
  group.add_option('--set-option', dest = 'set_options', action = 'append', default = [], metavar = 'SECTION:OPTION=VALUE', help = 'Set option')
  group.add_option('--add-option', dest = 'add_options', action = 'append', default = [], metavar = 'SECTION:OPTION=VALUE', help = 'Add value to an option')
  group.add_option('--enable-device', dest = 'enable_devices', action = 'append', default = [], metavar = 'DEVICE', help = 'Enable device')
  group.add_option('--disable-device', dest = 'disable_devices', action = 'append', default = [], metavar = 'DEVICE', help = 'Disable device')

  options, logger = parse_options(parser)

  if not options.file_in or not options.file_out:
    parser.print_help()
    sys.exit(1)

  if options.image == 'binary':
    with File.open(logger, options.file_in, 'r') as f_in:
      f_in.load()

      with BinaryFile.open(logger, options.file_out, 'w') as f_out:
        create_binary_image(logger, f_in, f_out, bio = options.bio)

  elif options.image == 'hdt':
    with BinaryFile.open(logger, options.file_out, 'w') as f_out:
      create_hdt_image(logger, options.file_in, f_out, options)
