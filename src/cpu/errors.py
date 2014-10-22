__all__ = ['CPUException', 'AccessViolationError', 'InvalidResourceError']

class CPUException(Exception):
  pass

class AccessViolationError(CPUException):
  pass

class InvalidResourceError(CPUException):
  pass

class MalformedBinaryError(CPUException):
  pass

