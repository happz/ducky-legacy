try:
  import cPickle as pickle

except ImportError:
  import pickle

from .util import BinaryFile, debug

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
      print offset, '  ', '%s: %s' % (field, getattr(self, field))

    if self.__children:
      print offset, '  children:'

      for name, value in self.__children.iteritems():
        if isinstance(value, SnapshotNode):
          print offset, '    ', '%s: %s' % (name, value.__class__.__name__)
          value.print_node(level = level + 2)

        else:
          print offset, '    ', '%s: %s' % (name, value)

class ISnapshotable(object):
  def save_state(self, parent):
    pass

  def load_state(self, state):
    pass

class VMState(SnapshotNode):
  @staticmethod
  def capture_vm_state(vm, suspend = True):
    debug('capture_vm_state')

    state = VMState()

    if suspend:
      debug('suspend vm...')
      vm.suspend()

    debug('capture state...')
    vm.save_state(state)

    if suspend:
      debug('wake vm up...')
      vm.wake_up()

    return state

  @staticmethod
  def load_vm_state(filename):
    return CoreDumpFile(filename, 'r').load()

  def save(self, filename):
    f_out = CoreDumpFile(filename, 'w')
    f_out.save(self)

class CoreDumpFile(BinaryFile):
  def load(self):
    debug('CoreDumpFile.load')

    return pickle.load(self)

  def save(self, state):
    debug('CoreDumpFile.save: state=%s', state)

    pickle.dump(state, self)
