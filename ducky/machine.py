"""
:py:class:`ducky.machine.Machine` is *the* virtual machine. Each instance
represents self-contained virtual machine, with all its devices, memory, CPUs
and other necessary properties.
"""

import itertools
import collections
import os
import sys
import time

from six import itervalues, iteritems
from collections import defaultdict, OrderedDict

from . import mm
from . import snapshot

from . import __version__

from .interfaces import IMachineWorker, ISnapshotable, IReactorTask

from .console import ConsoleMaster
from .errors import InvalidResourceError
from .log import create_logger
from .mm import UINT16_FMT
from .reactor import Reactor
from .snapshot import SnapshotNode
from .util import F
from .boot import ROMLoader

from functools import partial

class MachineState(SnapshotNode):
  def __init__(self):
    super(MachineState, self).__init__('nr_cpus', 'nr_cores')

  def get_cpu_states(self):
    return [__state for __name, __state in iteritems(self.get_children()) if __name.startswith('cpu')]

  def get_cpu_state_by_id(self, cpuid):
    return self.get_children()['cpu{}'.format(cpuid)]

class CommQueue(object):
  def __init__(self, channel):
    self.channel = channel

    self.queue_in = []
    self.queue_out = []

  def is_empty_out(self):
    return not bool(self.queue_out)

  def is_empty_in(self):
    return not bool(self.queue_in)

  def write_out(self, o):
    self.queue_out.append(o)

  def write_in(self, o):
    self.queue_in.append(o)

  def __read(self, queue):
    try:
      return queue.pop(0)

    except IndexError:
      return None

  def read_out(self):
    return self.__read(self.queue_out)

  def read_in(self):
    return self.__read(self.queue_in)

class CommChannel(object):
  def __init__(self, machine):
    self.machine = machine

    self._queues = {}

  def create_queue(self, name):
    queue = CommQueue(self)
    self._queues[name] = queue
    return queue

  def get_queue(self, name):
    return self._queues[name]

  def unregister_queue(self, name):
    del self._queues[name]


class IRQRouterTask(IReactorTask):
  """
  This task is responsible for distributing triggered IRQs between CPU cores.
  When IRQ is triggered, IRQ source (i.e. device that requires attention) is
  appended to this tasks queue (:py:attr:`ducky.machine.IRQRouterTask.qeueu`).
  As long as this queue is not empty, this task pops IRQ sources, selects
  free CPU core, and by calling its :py:meth:`ducky.cpu.CPUCore.irq` method
  core takes reponsibility for executing interrupt routine.

  :param ducky.machine.Machine machine: machine this task belongs to.
  """

  def __init__(self, machine):
    self.machine = machine

    from .devices import IRQList
    self.queue = [False for _ in range(0, IRQList.IRQ_COUNT)]

  def run(self):
    self.machine.DEBUG('irq: router has %i waiting irqs', self.queue.count(True))

    for irq, triggered in enumerate(self.queue):
      if triggered is not True:
        continue

      self.machine.DEBUG('irq: triggered %i', irq)
      for core in self.machine.living_cores:
        if core.hwint_allowed is not True:
          self.machine.DEBUG('irq: %s hwint not allowed', core.cpuid)
          continue

        self.machine.DEBUG('irq: interrupt %s', core.cpuid)

        self.queue[irq] = False
        core.irq(irq)
        break

      else:
        break

    if not any(self.queue):
      self.machine.reactor.task_suspended(self)

class HaltMachineTask(IReactorTask):
  def __init__(self, machine):
    self.machine = machine

  def run(self):
    self.machine.halt()

class EventBus(object):
  def __init__(self, machine):
    super(EventBus, self).__init__()

    self.machine = machine

    self.listeners = defaultdict(OrderedDict)

  def add_listener(self, event, callback, *args, **kwargs):
    self.machine.DEBUG('%s.add_listener: event=%s, callback=%s, args=%s, kwargs=%s', self.__class__.__name__, event, callback, args, kwargs)

    self.listeners[event][callback] = (args, kwargs)

  def remove_listener(self, event, callback):
    self.machine.DEBUG('%s.remove_listener: event=%s, callback=%s', self.__class__.__name__, event, callback)

    del self.listeners[event][callback]

  def trigger(self, event, *args, **kwargs):
    self.machine.DEBUG('%s.trigger: event=%s, args=%s, kwargs=%s', self.__class__.__name__, event, args, kwargs)

    for listener, (_args, _kwargs) in iteritems(self.listeners[event]):
      _args = _args + args
      _kwargs = _kwargs.copy()
      _kwargs.update(kwargs)
      listener(*args, **kwargs)

class Machine(ISnapshotable, IMachineWorker):
  """
  Virtual machine itself.
  """

  def core(self, cid):
    """
    Find CPU core by its string id.

    :param string cid: id of searched CPU core, in the form `#<cpuid>:#<coreid>`.
    :rtype: :py:class:`ducky.cpu.CPUCore`
    :returns: found core
    :raises ducky.errors.InvalidResourceError: when no such core exists.
    """

    for _cpu in self.cpus:
      for _core in _cpu.cores:
        if '#%i:#%i' % (_cpu.id, _core.id) == cid:
          return _core

    raise InvalidResourceError(F('No such CPU core: cid={cid}', cid = cid))

  def __init__(self, logger = None, stdin = None, stdout = None, stderr = None):
    self.stdin  = stdin or sys.stdin
    self.stdout = stdout or sys.stdout
    self.stderr = stderr or sys.stderr

    self.reactor = Reactor(self)

    # Setup logging
    self.LOGGER = logger or create_logger()
    self.DEBUG = self.LOGGER.debug
    self.INFO = self.LOGGER.info
    self.WARN = self.LOGGER.warning
    self.ERROR = self.LOGGER.error
    self.EXCEPTION = self.LOGGER.exception

    self._tenh = None
    self._tenh_device = None
    self._tenh_enabled = False

    self.console = ConsoleMaster(self)
    self.console.register_command('halt', cmd_halt)
    self.console.register_command('boot', cmd_boot)
    self.console.register_command('run', cmd_run)
    self.console.register_command('snap', cmd_snapshot)

    self.irq_router_task = IRQRouterTask(self)
    self.reactor.add_task(self.irq_router_task)

    self.check_living_cores_task = HaltMachineTask(self)
    self.reactor.add_task(self.check_living_cores_task)

    self.comm_channel = CommChannel(self)

    self.events = EventBus(self)

    self.living_cores = []

    self.running = False
    self.halted = False

    self.cpus = []
    self.memory = None

    self.devices = collections.defaultdict(dict)
    self.ports = {}

    self.virtual_interrupts = {}

    self.last_state = None

  @property
  def cores(self):
    """
    Get list of all cores in the machine.

    :rtype: list
    :returns: `list` of :py:class:`ducky.cpu.CPUCore` instances
    """

    return [c for c in itertools.chain(*[__cpu.cores for __cpu in self.cpus])]

  def on_core_alive(self, core):
    """
    Signal machine that one of CPU cores is now alive.
    """

    self.living_cores.append(core)

  def on_core_halted(self, core):
    """
    Signal machine that one of CPU cores is no longer alive.
    """

    self.living_cores.remove(core)

    if not self.living_cores:
      self.reactor.task_runnable(self.check_living_cores_task)

  def get_device_by_name(self, name, klass = None):
    """
    Get device by its name and class.

    :param string name: name of the device.
    :param string klass: if set, search only devices with this class.
    :rtype: :py:class:`ducky.devices.Device`
    :returns: found device
    :raises ducky.errors.InvalidResourceError: when no such device exists
    """

    self.DEBUG('get_device_by_name: name=%s, klass=%s', name, klass)

    for dev_klass, devs in iteritems(self.devices):
      if klass and dev_klass != klass:
        continue

      for dev_name, dev in iteritems(devs):
        if dev_name != name:
          continue

        return dev

    raise InvalidResourceError(F('No such device: name={name}, klass={klass}', name = name, klass = klass))

  def get_storage_by_id(self, sid):
    """
    Get storage by its id.

    :param int sid: id of storage caller is looking for.
    :rtype: :py:class:`ducky.devices.Device`
    :returns: found device.
    :raises ducky.errors.InvalidResourceError: when no such storage exists.
    """

    self.DEBUG('get_storage_by_id: id=%s', sid)
    self.DEBUG('storages: %s', self.devices['storage'])

    for name, dev in iteritems(self.devices['storage']):
      if dev.sid != sid:
        continue

      return dev

    raise InvalidResourceError(F('No such storage: sid={sid:d}', sid = sid))

  def save_state(self, parent):
    state = parent.add_child('machine', MachineState())

    state.nr_cpus = self.nr_cpus
    state.nr_cores = self.nr_cores

    for cpu in self.cpus:
      cpu.save_state(state)

    self.memory.save_state(state)

  def load_state(self, state):
    self.nr_cpus = state.nr_cpus
    self.nr_cores = state.nr_cores

    for __cpu in self.cpus:
      cpu_state = state.get_children().get('cpu{}'.format(__cpu.id))
      if cpu_state is None:
        self.WARN('State of CPU #%i not found!', __cpu.id)
        continue

      __cpu.load_state(cpu_state)

    self.memory.load_state(state.get_children()['memory'])

  def setup_devices(self):
    from .devices import get_driver_creator

    for section in self.config.iter_devices():
      _get, _getbool, _getint = self.config.create_getters(section)

      klass = _get('klass', None)
      driver = _get('driver', None)

      if not klass or not driver:
        self.ERROR('Unknown class or driver of device %s: klass=%s, driver=%s', section, klass, driver)
        continue

      if _getbool('enabled', True) is not True:
        self.DEBUG('Device %s disabled', section)
        continue

      dev = get_driver_creator(driver)(self, self.config, section)
      self.devices[klass][section] = dev

      if _get('master', None) is not None:
        dev.master = _get('master')

  def hw_setup(self, machine_config):
    self.config = machine_config

    self._tenh_enabled = machine_config.getbool('machine', 'tenh-enabled', False)

    self.nr_cpus = self.config.getint('machine', 'cpus')
    self.nr_cores = self.config.getint('machine', 'cores')

    # self.ivt_address = machine_config.getint('cpu', 'ivt-address', DEFAULT_IVT_ADDRESS)
    # self.pt_address = machine_config.getint('cpu', 'pt-address', DEFAULT_PT_ADDRESS)

    self.memory = mm.MemoryController(self, size = machine_config.getint('memory', 'size', 0x1000000))

    self.setup_devices()

    self.rom_loader = ROMLoader(self)

    from .cpu import CPU
    for cpuid in range(0, self.nr_cpus):
      self.cpus.append(CPU(self, cpuid, self.memory, cores = self.nr_cores))

    from .devices import VIRTUAL_INTERRUPTS
    for index, cls in iteritems(VIRTUAL_INTERRUPTS):
      self.virtual_interrupts[index] = cls(self)

  @property
  def exit_code(self):
    return max([c.exit_code for c in itertools.chain(*[__cpu.cores for __cpu in self.cpus])])

  def register_port(self, port, handler):
    self.DEBUG('Machine.register_port: port=%s, handler=%s', UINT16_FMT(port), handler)

    if port in self.ports:
      raise IndexError('Port already assigned: {}'.format(UINT16_FMT(port)))

    self.ports[port] = handler

  def unregister_port(self, port):
    self.DEBUG('Machine.unregister_port: port=%s', UINT16_FMT(port))

    del self.ports[port]

  def trigger_irq(self, handler):
    self.DEBUG('Machine.trigger_irq: handler=%s', handler)

    self.irq_router_task.queue[handler.irq] = True
    self.reactor.task_runnable(self.irq_router_task)

  def _do_tenh(self, printer, s, *args):
    printer('  ' + s + '\r\n', *args)
    self.INFO(s, *args)

  def tenh(self, s, *args):
    if not self._tenh_enabled:
      self.INFO(s, *args)
      return

    if self._tenh is None:
      for name, device in iteritems(self.devices['output']):
        if hasattr(device, 'tenh'):
          self._tenh_device = device
          self._tenh = partial(self._do_tenh, device.tenh)
          device.tenh_enable()
          break

      else:
        self._tenh = self.INFO

    self._tenh(s, *args)

  def boot(self):
    self.tenh('Ducky VM, version %s', __version__)
    self.tenh('Running on %s', sys.version.replace('\n', ' '))

    if self.config.getbool('machine', 'jit', False) is True:
      self.tenh('JIT enabled')

    self.DEBUG('Machine.boot')

    self.events.add_listener('on-core-alive', self.on_core_alive)
    self.events.add_listener('on-core-halted', self.on_core_halted)

    self.memory.boot()
    self.console.boot()

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.boot()

    self.rom_loader.boot()

    for __cpu in self.cpus:
      __cpu.boot()

    self.running = True

  def run(self):
    self.DEBUG('Machine.run')

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.run()

    for __cpu in self.cpus:
      __cpu.run()

    self.start_time = self.end_time = time.time()
    self.reactor.run()
    self.end_time = time.time()

  def suspend(self):
    self.DEBUG('Machine.suspend')

    for __cpu in self.cpus:
      __cpu.suspend()

  def wake_up(self):
    self.DEBUG('Machine.wake_up')

    for __cpu in self.cpus:
      __cpu.wake_up()

  def die(self, exc):
    self.DEBUG('Machine.die: exc=%s', exc)

    self.EXCEPTION(exc)

    self.halt()

  def halt(self):
    self.DEBUG('Machine.halt')

    self.capture_state()

    for __cpu in self.cpus:
      __cpu.halt()

    for devs in itervalues(self.devices):
      for dev in [dev for dev in itervalues(devs) if not dev.is_slave()]:
        dev.halt()

    self.rom_loader.halt()

    self.memory.halt()

    self.console.halt()

    self.reactor.remove_task(self.irq_router_task)
    self.reactor.remove_task(self.check_living_cores_task)

    self.events.remove_listener('on-core-alive', self.on_core_alive)
    self.events.remove_listener('on-core-halted', self.on_core_halted)

    self.tenh('Halted.')

    if self._tenh_enabled is True:
      self._tenh_device.tenh_flush_stream()
      self._tenh_device.tenh_close_stream()

    self.running = False
    self.halted = True

  def capture_state(self, suspend = False):
    """
    Capture current state of the VM, and store it in it's `last_state` attribute.

    :param bool suspend: if `True`, suspend VM before taking snapshot.
    """

    self.last_state = snapshot.VMState.capture_vm_state(self, suspend = suspend)
    return self.last_state

def cmd_boot(console, cmd):
  """
  Setup HW, load binaries, init everything
  """

  M = console.master.machine

  M.boot()
  M.console.unregister_command('boot')

def cmd_run(console, cmd):
  """
  Start execution of loaded binaries
  """

  M = console.master.machine

  M.run()
  M.console.unregister_command('run')

def cmd_halt(console, cmd):
  """
  Halt execution
  """

  M = console.master.machine

  M.halt()

  M.INFO('VM halted by user')

def cmd_snapshot(console, cmd):
  """
  Create snapshot
  """

  M = console.master.machine

  state = snapshot.VMState.capture_vm_state(M)

  filename = 'ducky-core.{}'.format(os.getpid())
  state.save(filename)

  M.INFO('Snapshot saved as %s', filename)
  console.writeln('Snapshot saved as %s', filename)
