import enum

from .util import UINT32_FMT

class Error(Exception):
  """
  Base class for all Ducky exceptions.

  :param str message: optional description.
  """

  def __init__(self, message = None):
    super(Error, self).__init__()

    self.message = message or ''

  def __str__(self):
    return self.message

  def log(self, logger):
    logger(self.message)

class InvalidResourceError(Error):
  """
  Raised when an operation was requested on somehow invalid resource.
  ``message`` attribute will provide better idea about the fault.
  """

  pass

class AccessViolationError(Error):
  """
  Raised when an operation was requested without having adequate permission
  to do so. ``message`` attribute will provide better idea about the fault.
  """

  pass

class AssemblerError(Error):
  """
  Base class for all assembler-related exceptions. Provides common properties,
  helping to locate related input in the source file.

  :param ducky.cpu.assembly.SourceLocation location: if set, points to the
    location in the source file that was processed when the exception occured.
  :param str message: more detailed description.
  :param str line: input source line.
  :param info: additional details of the exception. This value is usually part
    of the ``message``, but is stored as well.
  """

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

class ConflictingNamesError(AssemblerError):
  def __init__(self, **kwargs):
    super(ConflictingNamesError, self).__init__(message = 'Label already defined: {info}'.format(**kwargs), **kwargs)

class IncompatibleLinkerFlagsError(Error):
  pass

class UnknownSymbolError(Error):
  pass

class ExceptionList(enum.IntEnum):
  """
  List of exception IDs (``EVT`` indices).
  """

  FIRST_HW = 0
  LAST_HW  = 15

  FIRST_SW = 16
  LAST_SW  = 31

  COUNT    = 32

  # SW interrupts and exceptions
  InvalidOpcode    = 16
  InvalidInstSet   = 17
  DivideByZero     = 18
  UnalignedAccess  = 19
  PrivilegedInstr  = 20
  DoubleFault      = 21
  MemoryAccess     = 22
  RegisterAccess   = 23
  InvalidException = 24
  CoprocessorError = 25


class ExecutionException(Exception):
  """
  Base class for all execution-related exceptions, i.e. exceptions raised
  as a direct result of requests made by running code. Runnign code can then
  take care of handling these exceptions, usually by preparing service
  routines and setting up the ``IVT``.

  Unless said otherwise, the exception is always raised *before* making
  any changes in the VM state.

  :param string msg: message describing exceptional state.
  :param ducky.cpu.CPUCore core: CPU core that raised exception, if any.
  :param u32_t ip: address of an instruction that caused exception, if any.
  """

  def __init__(self, msg, core = None, ip = None):
    super(ExecutionException, self).__init__(msg)

    self.core = core
    self.ip = ip or (core.current_ip if core is not None else None)

  def __str__(self):
    return ' '.join([
      self.core.cpuid_prefix if self.core is not None else '<undef>:',
      UINT32_FMT(self.ip) if self.ip is not None else '<undef>:',
      self.message
    ])

  def runtime_handle(self):
    """
    This method is called by CPU code, to find out if it is possible for
    runtime to handle the exception, and possibly recover from it. If it
    is possible, this method should make necessary arrangements, and then
    return ``True``. Many exceptions, e.g. when division by zero was requested,
    will tell CPU to run exception service routine, and by returning ``True``
    signal that it's not necessary to take care of such exception anymore.

    :rtype: bool
    :returns: ``True`` when it's no longer necessary for VM code to take
      care of this exception.
    """

    pass

class ExecutionException__SimpleESR(object):
  """
  Helper mixin class - as one of parents, it brings to its children
  very simle - and most of the time sufficient - implementation of
  `runtime_handle` method. Such exceptions will tell CPU to run
  exception service routine with a secific index, specified by class
  variable ``EXCEPTION_INDEX``.

  The address of the offensive instruction - or the value of ``IP``
  when exception was raised, since there may be exceptions not raised
  in response to the executed instruction - is passed to CPU as the
  first argument of ESR.
  """

  def runtime_handle(self):
    self.core._handle_exception(self, self.__class__.EXCEPTION_INDEX, self.ip)
    return True

class InvalidOpcodeError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when unknown or invalid opcode is found in instruction.

  :param int opcode: wrong opcode.
  """

  EXCEPTION_INDEX = ExceptionList.InvalidOpcode

  def __init__(self, opcode, *args, **kwargs):
    super(InvalidOpcodeError, self).__init__('Invalid opcode: opcode={}'.format(opcode), *args, **kwargs)

    self.opcode = opcode

class DivideByZeroError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when divisor in a mathematical operation was equal to zero.
  """

  EXCEPTION_INDEX = ExceptionList.DivideByZero

  def __init__(self, *args, **kwargs):
    super(DivideByZeroError, self).__init__('Divide by zero not allowed', *args, **kwargs)

class PrivilegedInstructionError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when privileged instruction was about to be executed in non-privileged
  mode.
  """

  EXCEPTION_INDEX = ExceptionList.PrivilegedInstr

  def __init__(self, *args, **kwargs):
    super(PrivilegedInstructionError, self).__init__('Attempt to execute privileged instruction', *args, **kwargs)

class InvalidInstructionSetError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when switch to unknown or invalid instruction set was requested.

  :param int inst_set: instruction set id.
  """

  EXCEPTION_INDEX = ExceptionList.InvalidInstSet

  def __init__(self, inst_set, *args, **kwargs):
    super(InvalidInstructionSetError, self).__init__('Invalid instruction set requested: inst_set={}'.format(inst_set), *args, **kwargs)

    self.inst_set = inst_set

class UnalignedAccessError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when only properly aligned memory access is allowed, and running code
  attempts to access memory without honoring this restriction (e.g. ``LW``
  reading from byte-aligned address).
  """

  EXCEPTION_INDEX = ExceptionList.UnalignedAccess

  def __init__(self, *args, **kwargs):
    super(UnalignedAccessError, self).__init__('Invalid memory access alignment', *args, **kwargs)

class InvalidFrameError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when VM checks each call stack frame to be cleaned before it's left,
  and there are some values on stack when ``ret`` or ``retint`` are executed.
  In such case, the actual ``SP`` values does not equal to a saved one, and
  exception is raised.

  :param u32_t saved_sp: ``SP`` as saved at the moment the frame was created.
  :param u32_t current_sp: current ``SP``
  """

  def __init__(self, saved_sp, current_sp, *args, **kwargs):
    super(InvalidFrameError, self).__init__('Leaving weird frame: saved SP=%s, current SP=%s' % (UINT32_FMT(saved_sp), UINT32_FMT(current_sp)), *args, **kwargs)

    self.current_sp = current_sp
    self.saved_sp = saved_sp

  def runtime_handle(self):
    return False

class MemoryAccessError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when MMU decides the requested memory operation is now allowed, e.g.
  when page tables are enabled, and corresponding ``PTE`` denies write access.

  :param str access: ``read``, ``write`` or ``execute``.
  :param u32_t address: address where memory access shuld have happen.
  :param ducky.mm.PageTableEntry pte: ``PTE`` guarding this particular memory
    location.
  """

  EXCEPTION_INDEX = ExceptionList.MemoryAccess

  def __init__(self, access, address, pte, *args, **kwargs):
    super(MemoryAccessError, self).__init__('Memory access error: access=%s, address=%s, pte=%s' % ((access, UINT32_FMT(address), pte.to_string())))

    self.access = access
    self.address = address
    self.pte = pte.to_string()

class RegisterAccessError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when instruction tries to access a registerall which is not available
  for requested operation, e.g. writing into read-only control register will
  raise this exception.

  :param str access: ``read`` or ``write``.
  :param str reg: register name.
  """

  EXCEPTION_INDEX = ExceptionList.RegisterAccess

  def __init__(self, access, reg, *args, **kwargs):
    super(RegisterAccessError, self).__init__('Register access error: access=%s, reg=%s' % (access, reg))

    self.access = access
    self.reg = reg

class InvalidExceptionError(ExecutionException__SimpleESR, ExecutionException):
  """
  Raised when requested exception index is invalid (out of bounds).
  """

  EXCEPTION_INDEX = ExceptionList.InvalidException

  def __init__(self, exc_index, *args, **kwargs):
    super(InvalidExceptionError, self).__init__('Invalid exception index: index=%s' % UINT32_FMT(exc_index))

    self.exc_index = exc_index

class CoprocessorError(ExecutionException__SimpleESR, ExecutionException):
  """
  Base class for coprocessor errors. Raised when coprocessors needs to signal
  its own exception, when none of alread yavailable exceptions would do.
  """

  EXCEPTION_INDEX = ExceptionList.CoprocessorError

  def __init__(self, msg, *args, **kwargs):
    super(CoprocessorError, self).__init__('Coprocessor error: %s' % msg)
