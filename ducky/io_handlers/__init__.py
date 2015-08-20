import enum

from .. import cpu

from ..mm import UINT16_FMT

class IOPorts(enum.IntEnum):
  PORT_COUNT = 65536

class IOHandler(object):
  def __init__(self, machine):
    super(IOHandler, self).__init__()

    self.machine = machine
    self.is_protected = False

  def boot(self):
    pass

  def run(self):
    pass

  def halt(self):
    pass

  def read_u8(self, port):
    handler_name = 'read_u8_{}'.format(port)

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to read from port: port={}'.format(port))

    return getattr(self, handler_name)()

  def read_u16(self, port):
    handler_name = 'read_u16_{}'.format(port)

    self.machine.DEBUG('read_u16: port=%s', port)

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to read from port: port={}'.format(port))

    return getattr(self, handler_name)()

  def write_u8(self, port, value):
    handler_name = 'write_u8_{}'.format(port)

    self.machine.DEBUG('write_u8: port=%s, value=%s', port, value)

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to write to port: port={}'.format(UINT16_FMT(port)))

    getattr(self, handler_name)(value)

  def write_u16(self, port, value):
    handler_name = 'write_u16_{}'.format(port)

    self.machine.DEBUG('write_u16: port=%s, value=%s', port, value)

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to write to port: port={}'.format(UINT16_FMT(port)))

    getattr(self, handler_name)(value)

class IOPortSet(object):
  def __init__(self):
    super(IOPortSet, self).__init__()

    self.__ports = {}

  def __getitem__(self, port):
    return self.__ports.get(port)

  def __setitem__(self, port, handler):
    self.__ports[port] = handler

  def __delitem__(self, port):
    del self.__ports[port]

  def __len__(self):
    return len(self.__ports)

  def __contains__(self, port):
    return port in self.__ports

  def __iter__(self):
    return iter({}.fromkeys(self.__ports.values()).keys())
