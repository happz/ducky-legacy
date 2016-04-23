import six.moves
import urllib

if not hasattr(urllib, 'parse'):
  urllib.parse = six.moves.urllib.parse

from .. import patch  # noqa
from ..machine import Machine
from ..util import str2int, UINT32_FMT
from ..streams import OutputStream, InputStream
from ..interfaces import IReactorTask
from ..profiler import STORE

import optparse
import os
import signal
import sys
import threading

from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

class WSOutputStream(OutputStream):
  """
  Websocket output stream, receiving bytes from TTY frontend, and pushing them
  to protocol's socket.

  :param DuckyProtocol protocol: protocol instance with opened websocket.
  """

  def __init__(self, protocol, *args, **kwargs):
    super(WSOutputStream, self).__init__(*args, **kwargs)

    self._protocol = protocol

  def write(self, buff):
    """
    Write buffer into the socket.

    Called by device from machine thread, therefore this method hands buffer
    over to the reactor thread.

    :param bytearray buff: bytes to send to client.
    """

    self.DEBUG('%s.write: buff=%s', self.__class__.__name__, buff)

    reactor.callFromThread(self._protocol.sendMessage, (''.join([chr(b) for b in buff])).encode('utf8'), isBinary = False)

class WSInputStream(InputStream):
  """
  Websocket input stream, receiving bytes from opened websocket, and pushing
  them to keyboard frontend device.

  Stream has an internal LIFO buffer that is being fed by protocol, and
  consumed by VM frontend device.

  :param DuckyProtocol protocol: protocol instance with opened websocket.
  """

  def __init__(self, protocol, *args, **kwargs):
    super(WSInputStream, self).__init__(*args, **kwargs)

    self._protocol = protocol
    self._buffer = []

    self._flush_task = None

  def has_poll_support(self):
    """
    See :py:meth:`ducky.streams.Stream.has_poll_support'.

    """

    return True

  def register_with_reactor(self, reactor, on_read = None, on_error = None):
    """
    See :py:meth:`ducky.streams.Stream.register_with_reactor'.

    """

    input_buffer = self._buffer

    class FlushTask(IReactorTask):
      def run(self):
        if not input_buffer:
          return

        on_read()

    self._flush_task = FlushTask()
    reactor.add_task(self._flush_task)
    reactor.task_runnable(self._flush_task)

  def unregister_with_reactor(self, reactor):
    """
    See :py:meth:`ducky.streams.Stream.unregister_with_reactor'.

    """

    reactor.remove_task(self._flush_task)

  def enqueue(self, buff):
    """
    Called by protocol instance, to add newly received data to stream's
    buffer.

    :param bytearray buff: recerived bytes.
    """

    for c in buff:
      self._buffer.append(ord(c))

  def read(self, size = None):
    """
    See :py:meth:`ducky.streams.Stream.read'.

    """

    self.DEBUG('%s.read: size=%s', self.__class__.__name__, size)

    ret = []
    if size is None:
      while self._buffer:
        ret.append(self._buffer.pop(0))

    else:
      i = 0
      while self._buffer and i < size:
        ret.append(self._buffer.pop(0))
        i += 1

    if not ret:
      return None

    return ret

def print_machine_stats(logger, M):
  table_exits = [
    ['Core', 'Exit code']
  ]

  table_inst_caches = [
    ['Core', 'Reads', 'Inserts', 'Hits', 'Misses', 'Prunes']
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
  logger.table(table_cnts)
  logger.info('')

  inst_executed = sum([core.registers.cnt.value for core in M.cores])
  runtime = float(M.end_time - M.start_time)
  if runtime > 0:
    logger.info('Executed instructions: %i %f (%.4f/sec)', inst_executed, runtime, float(inst_executed) / runtime)
  logger.info('')

class DuckyProtocol(WebSocketServerProtocol):
  """
  Protocol handling communication between VM and remote terminal emulator.

  :param logging.Logger logger: ``Logger`` instanceto use for logging.
  :param options: command-line options, as returned by option parser.
  :param ducky.config.MachineConfig config: VM configuration.
  """

  _machines = []

  def __init__(self, logger, options, config):
    super(DuckyProtocol, self).__init__()

    self._logger = logger
    self._options = options
    self._config = config

    self.DEBUG = logger.debug

    self._machine = Machine()
    self._machine_thread = None
    self._input_stream = None

    self._profiler = None

  def onMessage(self, payload, isBinary):
    """
    Called when new data arrived from client. Feeds the data to VM's
    input stream.

    See :py:meth:`autobahn.twisted.websocket.WebSocketServerProtocol.onMessage`.
    """

    self.DEBUG('%s.onMessage', self.__class__.__name__)

    try:
      if self._input_stream is None:
        return

      self._input_stream.enqueue(payload)

    except Exception as e:
      self._logger.exception(e)
      self.sendClose()

  def run_machine(self):
    """
    Wraps VM's ``run()`` method by ``try/except`` clause, and call protocols
    ``sendClose()`` method when VM finishes.

    This is the target of VM`s thread.
    """

    try:
      if self._options.profile:
        self._profiler = STORE.get_machine_profiler()
        self._profiler.enable()

      self._machine.run()

    except Exception as e:
      self._logger.exception(e)

    finally:
      if self._profiler is not None:
        self._profiler.disable()

      reactor.callFromThread(self.sendClose)

  def onOpen(self, *args, **kwargs):
    """
    Called when new client connects to the server.

    This callback will setup and start new VM, connecting it to remote terminal
    by wrapping this protocol instance in two streams (input/output), and spawn
    a fresh new thread for it.
    """

    try:
      self.DEBUG('%s.onOpen', self.__class__.__name__)

      self._machine.hw_setup(self._config)

      self._output_stream = WSOutputStream(self, self._machine, '<ws-out>', fd = 0, close = False, allow_close = False)
      self._input_stream = WSInputStream(self, self._machine, '<ws-in>', fd = 0, close = False, allow_close = False)
      self._machine.get_device_by_name('device-3', klass = 'terminal').enqueue_streams(streams_in = [self._input_stream], stream_out = self._output_stream)

      self._machine.boot()

      for poke in self._options.poke:
        address, value, length = poke.split(':')

        if length not in ('1', '2', '4'):
          raise ValueError('Unknown poke size: poke=%s' % poke)

        self._machine.poke(str2int(address), str2int(value), str2int(length))

      self._machines.append(self._machine)

      self._machine_thread = threading.Thread(target = self.run_machine)
      self._machine_thread.start()

    except Exception as e:
      self._logger.exception(e)
      self.sendClose()

  def onClose(self, wasClean, code, reason):
    """
    Called when connection ends. Tell VM to halt, and wait for its thread
    to finish. Then, print some VM stats.
    """

    self.DEBUG('%s.onClose', self.__class__.__name__)

    if self._machine.halted is not True:
      from ..reactor import CallInReactorTask
      self._machine.reactor.add_event(CallInReactorTask(self._machine.halt))

      if self._machine_thread is not None:
        self._machine_thread.join()

    print_machine_stats(self._logger, self._machine)

    self._machines.remove(self._machine)

class DuckySocketServerFactory(WebSocketServerFactory):
  def __init__(self, logger, options, config, *args, **kwargs):
    super(DuckySocketServerFactory, self).__init__(*args, **kwargs)

    self._logger = logger
    self._options = options
    self._config = config

  def buildProtocol(self, *args, **kwargs):
    proto = DuckyProtocol(self._logger, self._options, self._config)
    proto.factory = self
    return proto

def process_config_options(logger, options, config_file = None, set_options = None, add_options = None, enable_devices = None, disable_devices = None):
  """
  Load VM config file, and apply all necessary changes, as requested by command-line options.

  :param logging.Logger logger: ``Logger`` instance to use for logging.
  :param options: command-line options, as returned by option parser.
  :param string config_file: path to configuration file.
  :rtype: ducky.config.MachineConfig
  :returns: VM configuration.
  """

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

    if not config.has_option(section, option):
      config.set(section, option, value)

    else:
      config.set(section, option, config.get(section, option) + ', ' + value)

  for dev in enable_devices:
    config.set(dev, 'enabled', True)

  for dev in disable_devices:
    config.set(dev, 'enabled', False)

  if 'JIT' in os.environ:
    config.set('machine', 'jit', os.environ['JIT'] == 'yes')

  else:
    config.set('machine', 'jit', options.jit is True)

  return config

def main():
  from . import add_common_options, parse_options

  parser = optparse.OptionParser()
  add_common_options(parser)

  # Machine configuration
  opt_group = optparse.OptionGroup(parser, 'Machine hardware')
  parser.add_option_group(opt_group)
  opt_group.add_option('--machine-config',  dest = 'machine_config',  action = 'store',      default = None,  help = 'Path to machine configuration file')
  opt_group.add_option('--machine-profile', dest = 'machine_profile', action = 'store_true', default = False, help = 'Enable profiling of running binaries')
  opt_group.add_option('--set-option',      dest = 'set_options',     action = 'append',     default = [],    metavar = 'SECTION:OPTION=VALUE', help = 'Set option')
  opt_group.add_option('--add-option',      dest = 'add_options',     action = 'append',     default = [],    metavar = 'SECTION:OPTION=VALUE')
  opt_group.add_option('--enable-device',   dest = 'enable_devices',  action = 'append',     default = [],    metavar = 'DEVICE', help = 'Enable device')
  opt_group.add_option('--disable-device',  dest = 'disable_devices', action = 'append',     default = [],    metavar = 'DEVICE', help = 'Disable device')
  opt_group.add_option('--poke',            dest = 'poke',            action = 'append',     default = [],    metavar = 'ADDRESS:VALUE:<124>', help = 'Modify content of memory before running binaries')
  opt_group.add_option('--jit',             dest = 'jit',             action = 'store_true', default = False, help = 'Optimize instructions')

  # Network options
  opt_group = optparse.OptionGroup(parser, 'Network options')
  parser.add_option_group(opt_group)
  opt_group.add_option('--network', dest = 'network', action = 'store_true', default = False, help = 'Start network service')
  opt_group.add_option('--host', dest = 'host', action = 'store', default = '', metavar = 'HOST', help = 'Listen at HOST address')
  opt_group.add_option('--port', dest = 'port', action = 'store', type = 'int', default = 19000, metavar = 'PORT', help = 'Listen at PORT port')
  opt_group.add_option('--queue', dest = 'queue', action = 'store', type = 'int', default = 10, metavar = 'LENGTH', help = 'Listen queue is LENGTH at max')

  # Debugging options
  opt_group = optparse.OptionGroup(parser, 'Debugging options')
  parser.add_option_group(opt_group)
  opt_group.add_option('--profile', dest = 'profile', action = 'store_true', default = False, help = 'Enable profiler')
  opt_group.add_option('--profile-dir', dest = 'profile_dir', action = 'store', default = None, metavar = 'DIR', help = 'Save profiling data into DIR')

  options, logger = parse_options(parser)

  if options.machine_config is None:
    parser.print_help()
    sys.exit(1)

  if options.profile and options.profile_dir is None:
    parser.print_help()
    sys.exit(1)

  config = process_config_options(logger,
                                  options,
                                  config_file = options.machine_config,
                                  set_options = [(section,) + tuple(option.split('=')) for section, option in (option.split(':') for option in options.set_options)],
                                  add_options = [(section,) + tuple(option.split('=')) for section, option in (option.split(':') for option in options.add_options)],
                                  enable_devices = options.enable_devices,
                                  disable_devices = options.disable_devices)

  if options.profile:
    STORE.enable_machine()

  main_thread_profiler = STORE.get_machine_profiler()
  main_thread_profiler.enable()

  if options.network is True:
    from twisted.python import log
    log.startLogging(sys.stdout)

    factory = DuckySocketServerFactory(logger, options, config)
    factory.protocol = DuckyProtocol

    reactor.listenTCP(options.port, factory, backlog = options.queue, interface = options.host)
    reactor.run()

    exit_code = 0

  else:
    M = Machine()
    M.hw_setup(config)

    def signal_handler(sig, frame):
      if sig == signal.SIGUSR1:
        M.tenh('VM suspended by user')
        M.reactor.add_call(M.suspend)

      elif sig == signal.SIGUSR2:
        M.tenh('VM unsuspended by user')
        M.reactor.add_call(M.wake_up)

      elif sig == signal.SIGINT:
        M.tenh('VM halted by user')
        M.reactor.add_call(M.halt)

      elif sig == signal.SIGSEGV:
        M.tenh('VM snapshot requested')
        M.reactor.add_call(M.snapshot('ducky-snapshot-user.bin'))

    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGUSR1, signal_handler)
    signal.signal(signal.SIGUSR2, signal_handler)
    signal.signal(signal.SIGSEGV, signal_handler)

    M.boot()

    for poke in options.poke:
      address, value, length = poke.split(':')

      if length not in ('1', '2', '4'):
        raise ValueError('Unkn poke size: poke=%s' % poke)

      M.poke(str2int(address), str2int(value), str2int(length))

    M.run()

    print_machine_stats(logger, M)
    exit_code = 1 if M.exit_code != 0 else 0

  main_thread_profiler.disable()

  if options.profile:
    logger.info('Saving profiling data into %s' % options.profile_dir)
    STORE.save(logger, options.profile_dir)

  sys.exit(exit_code)
