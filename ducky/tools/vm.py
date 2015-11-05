from ..import patch

import optparse
import signal
import sys

from six.moves import input

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
  opt_group.add_option('--set-device-option',
                       dest = 'set_device_options',
                       action = 'append',
                       default = [],
                       metavar = 'DEVICE:OPTION=VALUE',
                       help = 'Set device options')
  opt_group.add_option('--add-device-option',
                       dest = 'add_device_options',
                       action = 'append',
                       default = [],
                       metavar = 'DEVICE:OPTION=VALUE')
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
  opt_group.add_option('--debug-open-files', dest = 'debug_open_files', action = 'store_true', default = False, help = 'List all open - not closed cleanly - files when VM quits')
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

  from ..config import MachineConfig
  machine_config = MachineConfig()

  if options.machine_config is not None:
    machine_config.read(options.machine_config)

  for option in options.set_options:
    section, option = option.split(':')

    if not machine_config.has_section(section):
      logger.error('Unknown config section %s', section)
      continue

    option, value = option.split('=')

    machine_config.set(section, option, value)

  for option in options.add_options:
    section, option = option.split(':')

    if not machine_config.has_section(section):
      logger.error('Unknown config section %s', section)
      continue

    option, value = option.split('=')
    machine_config.set(section, option, machine_config.get(section, option) + ', ' + value)

  for option in options.set_device_options:
    dev, option = option.split(':')

    if not machine_config.has_section(dev):
      logger.error('Unknown device %s', dev)
      continue

    option, value = option.split('=')

    machine_config.set(dev, option, value)

  for option in options.add_device_options:
    dev, option = option.split(':')

    if not machine_config.has_section(dev):
      logger.error('Unknown device %s', dev)
      continue

    option, value = option.split('=')
    machine_config.set(dev, option, machine_config.get(dev, option) + ', ' + value)

  for dev in options.enable_devices:
    machine_config.set(dev, 'enabled', True)

  for dev in options.disable_devices:
    machine_config.set(dev, 'enabled', False)

  M.hw_setup(machine_config)

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
    table_exits.append([str(core), core.exit_code])

    table_inst_caches.append([
      str(core),
      core.instruction_cache.reads,
      core.instruction_cache.inserts,
      core.instruction_cache.hits,
      core.instruction_cache.misses,
      core.instruction_cache.prunes
    ])

    if core.data_cache is not None:
      table_data_caches.append([
        str(core),
        core.data_cache.reads,
        core.data_cache.hits,
        core.data_cache.misses,
        core.data_cache.prunes,
        core.data_cache.forced_writes
      ])

    table_cnts.append([
      str(core),
      core.registers.cnt.value
    ])

  for core in M.cores():
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

  inst_executed = sum([core.registers.cnt.value for core in M.cores()])
  runtime = float(M.end_time - M.start_time)
  logger.info('Executed instructions: %i %f (%.4f/sec)', inst_executed, runtime, float(inst_executed) / runtime)
  logger.info('')

  main_profiler.disable()

  if options.profile or options.machine_profile:
    logger.info('Saving profiling data into %s' % options.profile_dir)
    STORE.save(options.profile_dir)

  sys.exit(M.exit_code)
