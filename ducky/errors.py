class BaseException(Exception):
  def __init__(self, message = None):
    super(BaseException, self).__init__()

    self.message = message or ''

class InvalidResourceError(BaseException):
  pass

class AccessViolationError(BaseException):
  pass

class AssemblerError(BaseException):
  def __init__(self, filename, lineno, msg, line):
    super(AssemblerError, self).__init__(message = '{}:{}: {}'.format(filename, lineno, msg))

    self.filename = filename
    self.lineno   = lineno
    self._msg     = msg
    self.line     = line

class IncompleteDirectiveError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(IncompleteDirectiveError, self).__init__(filename, lineno, 'Incomplete directive: %s' % msg, line)

class UnknownFileError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(UnknownFileError, self).__init__(filename, lineno, 'Unknown file: %s' % msg, line)

class DisassembleMismatchError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(DisassembleMismatchError, self).__init__(filename, lineno, 'Disassembled instruction does not match input: %s' % msg, line)

class UnalignedJumpTargetError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(UnalignedJumpTargetError, self).__init__(filename, lineno, 'Jump destination address is not 4-byte aligned: %s' % msg, line)

class EncodingLargeValueError(AssemblerError):
  def __init__(self, filename, lineno, msg, line):
    super(EncodingLargeValueError, self).__init__(filename, lineno, 'Value cannot fit into field: %s' % msg, line)

class IncompatibleLinkerFlagsError(BaseException):
  pass
