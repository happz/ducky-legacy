import os
import sys

from ..mm import u32_t, PAGE_SIZE
from ..mm.binary import File, SectionTypes
from ..util import BinaryFile, align
from ..devices.storage import BLOCK_SIZE
from ..hdt import HDT
from ..log import get_logger

def align_file(f_out, boundary):
  D = get_logger().debug

  D('Adding padding bytes to align with BLOCK_SIZE')

  f_out.seek(0, os.SEEK_END)
  pos = f_out.tell()
  D('  Last position: %s => %s', pos, align(boundary, pos))

  missing = align(boundary, pos) - pos
  D('  Missing %s bytes', missing)

  f_out.write(bytearray([0] * missing))

def create_binary_image(f_in, f_out, bio = False):
  D = get_logger().debug

  D('create_binary_image: f_in=%s, f_out=%s, bio=%s', f_in.name, f_out.name, bio)

  reserved_space = BLOCK_SIZE

  for section in f_in.sections:
    D('Process section %s', section.name)

    if section.header.type != SectionTypes.PROGBITS:
      D('  Not a text or data section, ignore')
      continue

    if section.header.flags.loadable != 1:
      D('  Not loadable, ignore')
      continue

    D('  Base 0x%08X', section.header.base)
    D('  Seeking to %s', section.header.base + reserved_space)
    f_out.seek(section.header.base + reserved_space)

    if section.header.flags.bss == 1:
      f_out.write(bytearray([0] * section.header.data_size))

    else:
      f_out.write(section.payload)

  align_file(f_out, BLOCK_SIZE if bio else PAGE_SIZE)

  end = f_out.tell()
  D('Last position: %s', end)

  if bio is True:
    D('Writing header')

    f_out.seek(0)
    f_out.write(u32_t(end // BLOCK_SIZE))

  f_out.flush()

def create_hdt_image(file_in, f_out, options):
  logger = get_logger()

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

  align_file(f_out, PAGE_SIZE)

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
      with BinaryFile.open(logger, options.file_out, 'w') as f_out:
        create_binary_image(f_in, f_out, bio = options.bio)

  elif options.image == 'hdt':
    with BinaryFile.open(logger, options.file_out, 'w') as f_out:
      create_hdt_image(options.file_in, f_out, options)
