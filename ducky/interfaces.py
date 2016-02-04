class IMachineWorker(object):
  """
  Base class for objects that provide pluggable service to others.
  """

  def boot(self, *args):
    """
    Prepare for providing the service. After this call, it may be requested
    by others.
    """

    pass

  def run(self):
    """
    Called by reactor's loop when this object is enqueued as a reactor task.
    """

    pass

  def suspend(self):
    """
    Suspend service. Object should somehow conserve its internal state, its
    service will not be used until the next call of ``wake_up`` method.
    """

    pass

  def wake_up(self):
    """
    Wake up service. In this method, object should restore its internal state,
    and after this call its service can be requested by others again.
    """

    pass

  def die(self, exc):
    """
    Exceptional state requires immediate termination of service. Probably no
    object will ever have need to call others' ``die`` method, it's intended
    for internal use only.
    """

    pass

  def halt(self):
    """
    Terminate service. It will never be requested again, object can destroy
    its internal state, and free allocated resources.
    """

    pass


class IReactorTask(object):
  """
  Base class for all reactor tasks.
  """

  def run(self):
    """
    This method is called by reactor to perform task's actions.
    """

    pass

class ISnapshotable(object):
  """
  Base class for objects that can be saved into a snapshot.
  """

  def save_state(self, parent):
    """
    Create state of the object, and attach it to a parent snapshot node.

    :param ducky.interfaces.ISnapshotable parent: parent snapshot node.
    """

    pass

  def load_state(self, state):
    """
    Restore state of the object.

    :param ducky.snapshot.SnapshotNode state: snapshot node containing saved state.
    """

    pass


class IVirtualInterrupt(object):
  def __init__(self, machine):
    super(IVirtualInterrupt, self).__init__()

    self.machine = machine

  def run(self, core):
    pass
