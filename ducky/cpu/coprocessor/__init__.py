"""
Coprocessors are intended to extend operations of CPUs. They are optional, and
can cover wide range of operations, e.g. floating point arithmetic, encryption,
or graphics. They are always attached to a CPU core, and may contain and use
internal resources, e.g. their very own register sets, machine's memory, or
their parent's caches.
"""

class Coprocessor(object):
  """
  Base class for per-core coprocessors.
  """

  def __init__(self, core):
    super(Coprocessor, self).__init__()

    self.core = core
