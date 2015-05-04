try:
  from cProfile import Profile as RealMachineProfiler

except ImportError:
  from profile import Profile as RealMachineProfiler

try:
  import cPickle as pickle

except ImportError:
  import pickle

import collections
import os
import os.path

class DummyCPUCoreProfiler(object):
  def __init__(self, core, frequency = 17):
    super(DummyCPUCoreProfiler, self).__init__()

    self.core = core
    self.frequency = frequency

    self.enabled = False

  def enable(self):
    self.enabled = True

  def disable(self):
    self.enabled = False

  def take_sample(self):
    pass

  def create_stats(self):
    pass

  def dump_stats(self, filename):
    pass

class RealCPUCoreProfiler(DummyCPUCoreProfiler):
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
  def __init__(self, *args, **kwargs):
    super(DummyMachineProfiler, self).__init__()

  def enable(self):
    pass

  def disable(self):
    pass

  def create_stats(self):
    pass

  def dump_stats(self, filename):
    pass

class ProfilerStore(object):
  def __init__(self):
    super(ProfilerStore, self).__init__()

    self.machine_profiler_class = DummyMachineProfiler
    self.core_profiler_class    = DummyCPUCoreProfiler

    self.profilers = []

  def enable_machine(self):
    self.machine_profiler_class = RealMachineProfiler

  def enable_cpu(self):
    self.core_profiler_class = RealCPUCoreProfiler

  def is_machine_enabled(self):
    return self.machine_profiler_class == RealMachineProfiler

  def is_cpu_enabled(self):
    return self.core_profiler_class == RealCPUCoreProfiler

  def get_machine_profiler(self):
    p = self.machine_profiler_class(builtins = False)

    self.profilers.append(p)

    return p

  def get_core_profiler(self, core):
    p = self.core_profiler_class(core)

    self.profilers.append(p)

    return p

  def put_profiler(self, p):
    if not p:
      return

  def save(self, directory):
    filename_pattern = os.path.join(directory, 'profiler-%s-%s-%i.dat')

    for index, profiler in enumerate(self.profilers):
      profiler.disable()
      profiler.create_stats()
      profiler.dump_stats(filename_pattern % (os.getpid(), profiler.__class__.__name__, index))

STORE = ProfilerStore()
