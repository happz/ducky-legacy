class Error(Exception):
  def __init__(self, message = None):
    super(Error, self).__init__()

    self.message = message or ''

  def __str__(self):
    return self.message

class InvalidResourceError(Error):
  pass

class AccessViolationError(Error):
  pass

class AssemblerError(Error):
  def __init__(self, location = None, message = None, line = None, info = None):
    self.location = location
    self.message  = message
    self.line     = line
    self.info     = info

    self.create_text()

    super(AssemblerError, self).__init__(message = self.text[0])

  def create_text(self):
    text = ['{coor}: {message}'.format(coor = str(self.location), message = self.message)]

    if self.line is not None:
      text.append(self.line)

    if self.location.column is not None:
      text.append(' ' * self.location.column + '^')

    self.text = text

  def log(self, logger):
    logger('')
    for line in self.text:
      logger(line)

class TooManyLabelsError(AssemblerError):
  def __init__(self, **kwargs):
    super(TooManyLabelsError, self).__init__(message = 'Too many consecutive labels', **kwargs)

class UnknownPatternError(AssemblerError):
  def __init__(self, **kwargs):
    super(UnknownPatternError, self).__init__(message = 'Unknown pattern: "{info}"'.format(**kwargs), **kwargs)

class IncompleteDirectiveError(AssemblerError):
  def __init__(self, **kwargs):
    super(IncompleteDirectiveError, self).__init__(message = 'Incomplete directive: {info}'.format(**kwargs), **kwargs)

class UnknownFileError(AssemblerError):
  def __init__(self, **kwargs):
    super(UnknownFileError, self).__init__(message = 'Unknown file: {info}'.format(**kwargs), **kwargs)

class DisassembleMismatchError(AssemblerError):
  def __init__(self, **kwargs):
    super(DisassembleMismatchError, self).__init__(message = 'Disassembled instruction does not match input: {info}'.format(**kwargs), **kwargs)

class UnalignedJumpTargetError(AssemblerError):
  def __init__(self, **kwargs):
    super(UnalignedJumpTargetError, self).__init__(message = 'Jump destination address is not 4-byte aligned: {info}'.format(**kwargs), **kwargs)

class EncodingLargeValueError(AssemblerError):
  def __init__(self, **kwargs):
    super(EncodingLargeValueError, self).__init__(message = 'Value cannot fit into field: {info}'.format(**kwargs), **kwargs)

class IncompatibleLinkerFlagsError(Error):
  pass

class UnknownSymbolError(Error):
  pass
