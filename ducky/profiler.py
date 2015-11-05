"""
This module provides support for profiling the virtual machine (`machine`
profilers) and running programs (`code` profilers). Wrappers for python's
deterministic profilers, and simple statistical profiler of running code
are available for usage thoughout the ducky sources.

``cProfile`` is the prefered choice of machine profiling backend, with
``profile`` is used as a backup option.

Beware, each thread needs its own profiler instance. These instances can be
acquired from ProfilerStore class which handles saving their data when virtual
machine exits.

To simplify the usage of profilers in ducky sources in case when user does not
need profiling, I chose to provide classes with the same API but these classes
does not capture any data. These are called `dummy` profilers, as opposed to
the `real` ones. Both kinds mimic API of :py:class:`profile.Profile` - the
`real` machine profiler **is** :py:class:`profile.Profile` object.
"""

import collections
import os
import os.path

from six.moves import cPickle as pickle

try:
  from cProfile import Profile as RealMachineProfiler

except ImportError:
  from profile import Profile as RealMachineProfiler

class DummyCPUCoreProfiler(object):
  """
  Dummy code profiler class. Base class for all code profilers.

  :param ducky.cpu.CPUCore core: core this profiler captures data from.
  :param int frequency: sampling frequency, given as an instruction count.
  """

  def __init__(self, core, frequency = 17):
    super(DummyCPUCoreProfiler, self).__init__()

    self.core = core
    self.frequency = frequency

    self.enabled = False

  def enable(self):
    """
    Enable collection of profiling data.
    """

    self.enabled = True

  def disable(self):
    """
    Disable collection of profiling data.
    """

    self.enabled = False

  def take_sample(self):
    """
    Take a sample of current state of CPU core, and store any necessary data.
    """

    pass

  def create_stats(self):
    """
    Preprocess collected data before they can be printed, searched or saved.
    """

    pass

  def dump_stats(self, filename):
    """
    Save collected data into file.

    :param string filename: path to file.
    """

    pass

class RealCPUCoreProfiler(DummyCPUCoreProfiler):
  """
  Real code profiler. This class actually does collect data.
  """

  def __init__(self, core):
    super(RealCPUCoreProfiler, self).__init__(core)

    self.data = []

  def take_sample(self):
    if self.enabled is not True:
      return

    if self.core.registers.cnt.value % self.frequency != 0:
      return

    self.data.append(self.core.current_ip)

  def dump_stats(self, filename):
    d = collections.defaultdict(int)

    for e in self.data:
      d[e] += 1

    with open(filename, 'wb') as f:
      pickle.dump(d, f)

class DummyMachineProfiler(object):
  """
  Dummy machine profiler. Does absolutely nothing.
  """

  def __init__(self, *args, **kwargs):
    super(DummyMachineProfiler, self).__init__()

  def enable(self):
    """
    Start collecting profiling data.
    """

    pass

  def disable(self):
    """
    Stop collecting profiling data.
    """

    pass

  def create_stats(self):
    """
    Preprocess collected data before they can be printed, searched or saved.
    """

    pass

  def dump_stats(self, filename):
    """
    Save collected data into file.

    :param string filename: path to file.
    """

    pass

class ProfilerStore(object):
  """
  This class manages profiler instances. When in need of a profiler (e.g. in a
  new thread) get one by calling proper method of ProfilerStore object.
  """

  def __init__(self):
    super(ProfilerStore, self).__init__()

    self.machine_profiler_class = DummyMachineProfiler
    self.core_profiler_class    = DummyCPUCoreProfiler

    self.profilers = []

  def enable_machine(self):
    """
    Each newly created virtual machine profiler will be the real one.
    """

    self.machine_profiler_class = RealMachineProfiler

  def enable_cpu(self):
    """
    Each newly created code profiler will be the real one.
    """

    self.core_profiler_class = RealCPUCoreProfiler

  def is_machine_enabled(self):
    """
    Returns ``True`` when virtual machine profiling is enabled.

    :rtype: bool
    """

    return self.machine_profiler_class == RealMachineProfiler

  def is_cpu_enabled(self):
    """
    Returns ``True`` when code profiling is enabled.

    :rtype: bool
    """

    return self.core_profiler_class == RealCPUCoreProfiler

  def get_machine_profiler(self):
    """
    Create and return new machine profiler.

    :returns: new machine profiler.
    """

    p = self.machine_profiler_class(builtins = False)

    self.profilers.append(p)

    return p

  def get_core_profiler(self, core):
    """
    Create new code profiler.

    :rtype: DummyCPUCoreProfiler
    """

    p = self.core_profiler_class(core)

    self.profilers.append(p)

    return p

  def save(self, directory):
    """
    Save all captured data to files. Each created profiler stores its data in
    separate file.

    :param string directory: directory where all files are stored.
    """

    filename_pattern = os.path.join(directory, 'profiler-%s-%s-%i.dat')

    for index, profiler in enumerate(self.profilers):
      profiler.disable()
      profiler.create_stats()
      profiler.dump_stats(filename_pattern % (os.getpid(), profiler.__class__.__name__, index))

#: Main profiler store
STORE = ProfilerStore()
