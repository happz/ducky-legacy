try:
  import cPickle as pickle

except ImportError:
  import pickle

from .util import BinaryFile

class SnapshotNode(object):
  def __init__(self, *fields):
    self.__children = {}
    self.__fields = fields

    for field in fields:
      setattr(self, field, None)

  def add_child(self, name, child):
    self.__children[name] = child
    return child

  def get_child(self, name):
    return self.__children[name]

  def get_children(self):
    return self.__children

  def print_node(self, level = 0):
    offset = '    ' * level

    print offset, self.__class__.__name__

    for field in self.__fields:
      print offset, '  ', '{}: {}'.format(field, getattr(self, field))

    if self.__children:
      print offset, '  children:'

      for name, value in self.__children.iteritems():
        if isinstance(value, SnapshotNode):
          print offset, '    ', '{}: {}'.format(name, value.__class__.__name__)
          value.print_node(level = level + 2)

        else:
          print offset, '    ', '{}: {}'.format(name, value)

class VMState(SnapshotNode):
  def __init__(self, logger):
    super(VMState, self).__init__()

    self.logger = logger

  @staticmethod
  def capture_vm_state(machine, suspend = True):
    machine.DEBUG('capture_vm_state')

    state = VMState(machine.LOGGER)

    if suspend:
      machine.DEBUG('suspend vm...')
      machine.suspend()

    machine.DEBUG('capture state...')
    machine.save_state(state)

    if suspend:
      machine.DEBUG('wake vm up...')
      machine.wake_up()

    return state

  @staticmethod
  def load_vm_state(logger, filename):
    return CoreDumpFile(logger, filename, 'r').load()

  def save(self, filename):
    with CoreDumpFile(self.logger, filename, 'w') as f_out:
      f_out.save(self)

class CoreDumpFile(BinaryFile):
  def load(self):
    self.DEBUG('CoreDumpFile.load')

    return pickle.load(self)

  def save(self, state):
    self.DEBUG('CoreDumpFile.save: state=%s', state)

    logger, state.logger = state.logger, None
    pickle.dump(state, self)
    state.logger = logger
