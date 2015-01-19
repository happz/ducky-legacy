__all__ = ['CPUException', 'AccessViolationError', 'InvalidResourceError', 'MalformedBinaryError']

class CPUException(Exception):
  pass

class AccessViolationError(CPUException):
  pass

class InvalidResourceError(CPUException):
  pass

class MalformedBinaryError(CPUException):
  pass

class CompilationError(Exception):
  pass

class InvalidOpcode(CPUException):
  def __init__(self, opcode, ip = None):
    msg = 'Invalid opcode: opcode=%i, ip=%s' % (opcode, ip) if ip else 'Invalid opcode: opcode=%i' % opcode

    super(InvalidOpcode, self).__init__(msg)

    self.opcode = opcode
    self.ip = ip
