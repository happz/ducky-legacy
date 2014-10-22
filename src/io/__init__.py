import enum

import cpu

from util import *

class IOPorts(enum.Enum):
  PORT_COUNT = 65536

class IOHandler(object):
  def __init__(self, cpu):
    super(IOHandler, self).__init__()

    self.cpu = cpu

    self.is_protected = False

  def read_u8(self, port):
    handler_name = 'read_u8_%i' % port.u16

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to read from port: port=%i' % port.u16)

    return getattr(self, handler_name)()

  def read_u16(self, port):
    handler_name = 'read_u16_%i' % port.u16

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to read from port: port=%i' % port.u16)

    return getattr(self, handler_name)()

  def write_u8(self, port, value):
    handler_name = 'write_u8_%i' % port.u16

    debug('write_u8: port=0x%X, value=0x%X' % (port.u16, value.u8))

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to write to port: port=%i' % port.u16)

    getattr(self, handler_name)(value)

  def write_u16(self, port, value):
    handler_name = 'write_u16_%i' % port.u16

    debug('write_u16: port=0x%X, value=0x%X' % (port.u16, value.u16))

    if not hasattr(self, handler_name):
      raise cpu.AccessViolationError('Unable to write to port: port=%i' % port.u16)

    getattr(self, handler_name)(value)

class IOPortSet(object):
  def __init__(self):
    super(IOPortSet, self).__init__()

    self.__ports = {}

  def __getitem__(self, port):
    return self.__ports.get(port, None)

  def __setitem__(self, port, handler):
    self.__ports[port] = handler

  def __delitem__(self, port):
    del self.__ports[port]

  def __len__(self):
    return len(self.__ports)

  def __contains__(self, port):
    return port in self.__ports

