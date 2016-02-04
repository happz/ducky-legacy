from .. import patch
from ..util import str2int, UINT32_FMT

import optparse
import signal
import sys

from six.moves import input


def process_config_options(logger, config_file = None, set_options = None, add_options = None, enable_devices = None, disable_devices = None):
  logger.debug('process_config_options: config_file=%s, set_options=%s, add_options=%s, enable_devices=%s, disable_devices=%s', config_file, set_options, add_options, enable_devices, disable_devices)

  set_options = set_options or []
  add_options = add_options or []
  enable_devices = enable_devices or []
  disable_devices = disable_devices or []

  from ..config import MachineConfig
  config = MachineConfig()

  if config_file is not None:
    config.read(config_file)

  for section, option, value in set_options:
    if not config.has_section(section):
      logger.error('Unknown config section %s', section)
      continue

    config.set(section, option, value)

  for section, option, value in add_options:
    if not config.has_section(section):
      logger.error('Unknown config section %s', section)
      continue

    config.set(section, option, config.get(section, option) + ', ' + value)

  for dev in enable_devices:
    config.set(dev, 'enabled', True)

  for dev in disable_devices:
    config.set(dev, 'enabled', False)

  return config

def main():
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  # Machine configuration
  opt_group = optparse.OptionGroup(parser, 'Machine hardware')
  parser.add_option_group(opt_group)
  opt_group.add_option('--machine-config',
                       dest = 'machine_config',
                       action = 'store',
                       default = None,
                       help = 'Path to machine configuration file')
  opt_group.add_option('--machine-profile',
                       dest = 'machine_profile',
                       action = 'store_true',
                       default = False,
                       help = 'Enable profiling of running binaries')
  opt_group.add_option('--set-option',
                       dest = 'set_options',
                       action = 'append',
                       default = [],
                       metavar = 'SECTION:OPTION=VALUE',
                       help = 'Set option')
  opt_group.add_option('--add-option',
                       dest = 'add_options',
                       action = 'append',
                       default = [],
                       metavar = 'SECTION:OPTION=VALUE')
  opt_group.add_option('--enable-device',
                       dest = 'enable_devices',
                       action = 'append',
                       default = [],
                       metavar = 'DEVICE',
                       help = 'Enable device')
  opt_group.add_option('--disable-device',
                       dest = 'disable_devices',
                       action = 'append',
                       default = [],
                       metavar = 'DEVICE',
                       help = 'Disable device')
  opt_group.add_option('--poke', dest = 'poke', action = 'append', default = [], metavar = 'ADDRESS:VALUE:<124>', help = 'Modify content of memory before running binaries')

  # Debug options
  opt_group = optparse.OptionGroup(parser, 'Debug options')
  parser.add_option_group(opt_group)
  opt_group.add_option('-g', '--go-on',
                       dest = 'go_on',
                       action = 'store_true',
                       default = False,
                       help = 'Don\'t wait for user to start binaries with pressing Enter')
  opt_group.add_option('-p', '--profile',
                       dest = 'profile',
                       action = 'store_true',
                       default = False,
                       help = 'Enable profiling of the whole virtual machine')
  opt_group.add_option('-P', '--profile-dir',
                       dest = 'profile_dir',
                       action = 'store',
                       default = None,
                       help = 'Store profiling data in this directory')
  opt_group.add_option('--stdio-console',    dest = 'stdio_console',    action = 'store_true', default = False, help = 'Enable console terminal using stdin/stdout as IO streams')

  options, logger = parse_options(parser)

  if options.machine_config is None:
    parser.print_help()
    sys.exit(1)

  from ..profiler import STORE

  if options.profile:
    STORE.enable_machine()

  if options.machine_profile:
    STORE.enable_cpu()

  main_profiler = STORE.get_machine_profiler()
  main_profiler.enable()

  from ..machine import Machine
  M = Machine()

  if options.stdio_console:
    from ..console import TerminalConsoleConnection
    console_slave = TerminalConsoleConnection(0, M.console)
    console_slave.boot()
    M.console.connect(console_slave)

  config = process_config_options(logger,
                                  config_file = options.machine_config,
                                  set_options = [(section,) + tuple(option.split('=')) for section, option in [option.split(':') for option in options.set_options]],
                                  add_options = [(section,) + tuple(option.split('=')) for section, option in [option.split(':') for option in options.add_options]],
                                  enable_devices = options.enable_devices,
                                  disable_devices = options.disable_devices)

  M.hw_setup(config)

  def signal_handler(sig, frame):
    if sig == signal.SIGUSR1:
      logger.info('VM suspended by user')
      M.reactor.add_call(M.suspend)

    elif sig == signal.SIGUSR2:
      logger.info('VM unsuspended by user')
      M.reactor.add_call(M.wake_up)

    elif sig == signal.SIGINT:
      logger.info('VM halted by user')
      M.reactor.add_call(M.halt)

    elif sig == signal.SIGSEGV:
      logger.info('VM snapshot requested')
      M.reactor.add_call(M.snapshot('ducky-snapshot-user.bin'))

  signal.signal(signal.SIGINT,  signal_handler)
  signal.signal(signal.SIGUSR1, signal_handler)
  signal.signal(signal.SIGUSR2, signal_handler)
  signal.signal(signal.SIGSEGV, signal_handler)

  M.boot()

  for poke in options.poke:
    address, value, length = poke.split(':')

    if length not in ('1', '2', '4'):
      raise ValueError('Unknown poke size: poke=%s' % poke)

    M.poke(str2int(address), str2int(value), str2int(length))

  if not options.go_on:
    input('Press Enter to start execution of loaded binaries')

  M.run()  # reactor loop!

  table_exits = [
    ['Core', 'Exit code']
  ]

  table_inst_caches = [
    ['Core', 'Reads', 'Inserts', 'Hits', 'Misses', 'Prunes']
  ]
  table_data_caches = [
    ['Core', 'Reads', 'Hits', 'Misses', 'Prunes', 'Forced writes']
  ]
  table_cnts = [
    ['Core', 'Ticks']
  ]

  def __check_stats(core):
    table_exits.append([str(core), UINT32_FMT(core.exit_code)])

    table_inst_caches.append([
      str(core),
      core.mmu.instruction_cache.reads,
      core.mmu.instruction_cache.inserts,
      core.mmu.instruction_cache.hits,
      core.mmu.instruction_cache.misses,
      core.mmu.instruction_cache.prunes
    ])

    if core.mmu.data_cache is not None:
      table_data_caches.append([
        str(core),
        core.mmu.data_cache.reads,
        core.mmu.data_cache.hits,
        core.mmu.data_cache.misses,
        core.mmu.data_cache.prunes,
        core.mmu.data_cache.forced_writes
      ])

    table_cnts.append([
      str(core),
      core.registers.cnt.value
    ])

  for core in M.cores:
    __check_stats(core)

  logger.info('')
  logger.info('Exit codes')
  logger.table(table_exits)
  logger.info('')
  logger.info('Instruction caches')
  logger.table(table_inst_caches)
  logger.info('')
  logger.info('Data caches')
  logger.table(table_data_caches)
  logger.info('')
  logger.table(table_cnts)
  logger.info('')

  inst_executed = sum([core.registers.cnt.value for core in M.cores])
  runtime = float(M.end_time - M.start_time)
  logger.info('Executed instructions: %i %f (%.4f/sec)', inst_executed, runtime, float(inst_executed) / runtime)
  logger.info('')

  main_profiler.disable()

  if options.profile or options.machine_profile:
    logger.info('Saving profiling data into %s' % options.profile_dir)
    STORE.save(options.profile_dir)

  sys.exit(1 if M.exit_code != 0 else 0)
