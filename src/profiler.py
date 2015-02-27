try:
  from cProfile import Profile as RealMachineProfiler

except ImportError:
  from profile import Profile as RealMachineProfiler

import marshal
import os
import os.path
import threading2

class DummyCPUCoreProfiler(object):
  def __init__(self, core):
    super(DummyCPUCoreProfiler, self).__init__()

    self.core = core

  def trigger_jump(self, a, b):
    pass

  def enable(self):
    pass

  def disable(self):
    pass

  def trigger_ret(self, a, b):
    pass

  def create_stats(self):
    pass

  def dump_stats(self, filename):
    pass

class RealCPUCoreProfiler(DummyCPUCoreProfiler):
  def __init__(self, core):
    super(RealCPUCoreProfiler, self).__init__(core)

    self.data = []

  def trigger_jump(self, src_addr, dst_addr):
    self.data.append(('jump', src_addr, dst_addr))

  def trigger_ret(self, src_addr, dst_addr):
    self.data.append(('ret', src_addr, dst_addr))

  def dump_stats(self, filename):
    with open(filename, 'wb') as f:
      marshal.dump(self.data, f)

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

    self.lock = threading2.Lock()
    self.profilers = []

  def enable_machine(self):
    self.machine_profiler_class = RealMachineProfiler

  def enable_cpu(self):
    self.core_profiler_class = RealCPUCoreProfiler

  def is_machine_enabled(self):
    return self.machine_profiler_class == RealMachineProfiler

  def is_cpu_enabled(self):
    return self.core_profiler_class == CPUCoreprofiler

  def get_machine_profiler(self):
    p = self.machine_profiler_class(builtins = False)

    with self.lock:
      self.profilers.append(p)

    return p

  def get_cpu_profiler(self, core):
    p = self.core_profiler_class(core)

    with self.lock:
      self.profilers.append(p)

    return p

  def put_profiler(self, p):
    if not p:
      return

  def save(self, directory):
    filename_pattern = os.path.join(directory, 'profiler-' + str(os.getpid()) + '-%i.dat')

    for index, profiler in enumerate(self.profilers):
      profiler.disable()
      profiler.create_stats()
      profiler.dump_stats(filename_pattern % index)

STORE = ProfilerStore()

