try:
  from cProfile import Profile as RealProfiler

except ImportError:
  from profile import Profile as RealProfiler

import os.path
import threading2

class DummyProfiler(object):
  def __init__(self, *args, **kwargs):
    pass

  def enable(self):
    pass

  def disable(self):
    pass

class ProfilerStore(object):
  def __init__(self):
    super(ProfilerStore, self).__init__()

    self.profiler_class = DummyProfiler

    self.lock = threading2.Lock()
    self.profilers = []

  def enable(self):
    self.profiler_class = RealProfiler

  def is_enabled(self):
    return self.profiler_class == RealProfiler

  def get_profiler(self):
    p = self.profiler_class(builtins = False)

    with self.lock:
      self.profilers.append(p)

    return p

  def put_profiler(self, p):
    if not p:
      return

  def save(self, directory):
    if not self.is_enabled():
      return

    for index, profiler in enumerate(self.profilers):
      profiler.disable()
      profiler.create_stats()
      profiler.dump_stats(os.path.join(directory, 'profiler-%i.dat' % index))

STORE = ProfilerStore()

