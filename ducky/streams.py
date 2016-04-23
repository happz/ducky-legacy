"""
Streams represent basic IO objects, used by devices for reading or writing
(streams) of data.

``Stream`` object encapsulates an actual IO object - ``file``-like stream,
raw file descriptor, or even something completely different. ``Stream`` classes
then provide basic IO methods for moving data to and from stream, shielding
user from implementation details, like Python2/Python3 differencies.
"""

import abc
import errno
import fcntl
import io
import os
import termios
import tty

from six import PY2, integer_types, string_types, add_metaclass

from .errors import InvalidResourceError
from .util import isfile

def fd_blocking(fd, block = None):
  """
  Query or set blocking mode of file descriptor.

  :type int fd: file descriptor to manipulate.
  :type bool block: if set, method will set blocking mode of file descriptor
    accordingly: ``True`` means blocking, ``False`` non-blocking mode. If not
    set, the current setting will be returned. ``None`` by default.
  :rtype: bool
  :returns: if ``block`` is ``None``, current setting of blocking mode is
    returned - ``True`` for blocking, ``False`` for non-blocking. Othwerwise,
    function returns nothing.
  """

  flags = fcntl.fcntl(fd, fcntl.F_GETFL)

  if block is None:
    return (flags & os.O_NONBLOCK) == 0

  if block is True:
    flags &= ~os.O_NONBLOCK

  else:
    flags |= os.O_NONBLOCK

  fcntl.fcntl(fd, fcntl.F_SETFL, flags)

@add_metaclass(abc.ABCMeta)
class Stream(object):
  """
  Abstract base class of all streams.

  :param machine: parent :py:class`ducky.machine.Machine` object.
  :param desc: description of stream. This is a short, string representation
    of the stream.
  :param stream: ``file``-like stream that provides IO method (``read()`` or
    ``write``). If it is set, it is preferred IO object.
  :param int fd: raw file descriptor. ``stream`` takes precedence, otherwise this
    file descriptor is used.
  :param bool close: if ``True``, and if ``stream`` has a ``close()`` method, stream
    will provide ``close()`` method that will close the underlaying ``file``-like
    object. ``True`` by default.
  :param bool allow_close: if not ``True``, stream's ``close()`` method will *not*
    close underlying IO resource. ``True`` by default.
  """

  def __init__(self, machine, desc, stream = None, fd = None, close = True, allow_close = True):
    if stream is None and fd is None:
      raise InvalidResourceError('Stream "%s" must have stream object or raw file descriptor.' % desc)

    self.logger = machine.LOGGER
    self.DEBUG = machine.LOGGER.debug

    self.desc = desc
    self.stream = stream
    self.fd = fd

    self._raw_read = self._raw_read_stream if stream is not None else self._raw_read_fd
    self._raw_write = self._raw_write_stream if stream is not None else self._raw_write_fd

    self.allow_close = allow_close

    self._close = None
    if close is True and stream is not None and hasattr(stream, 'close'):
      self._close = stream.close

  def __repr__(self):
    return '<%s %s>' % (self.__class__.__name__, self.desc)

  def has_fd(self):
    """
    Check if stream has raw file descriptor. File descriptors can be checked
    for IO availability by reactor's polling task.

    :rtype: bool
    :returns: ``True`` when stream has file descriptor.
    """

    return self.fd is not None

  def has_poll_support(self):
    """
    Streams that can polled for data should return ``True``.

    :rtype: bool
    """

    # For most common case, if the stream has file descriptor set, it can be polled.
    return self.has_fd()

  def register_with_reactor(self, reactor, **kwargs):
    """
    Called by owner to register the stream with reactor's polling service.

    See :py:meth:`ducky.reactor.Reactor.add_fd` for keyword arguments.

    :param ducky.reactor.Reactor reactor: reactor instance to register with.
    """

    reactor.add_fd(self.fd, **kwargs)

  def unregister_with_reactor(self, reactor):
    """
    Called by owner to unregister the stream with reactor's polling service,
    e.g. when stream is about to be closed.

    :param ducky.reactor.Reactor reactor: reactor instance to unregister from.
    """

    reactor.remove_fd(self.fd)

  def _raw_read_stream(self, size = None):
    self.DEBUG('%s._raw_read_stream: size=%s', self.__class__.__name__, size)

    size = size or 0
    return self.stream.read(size)

  def _raw_read_fd(self, size = None):
    self.DEBUG('%s._raw_read_fd: size=%s', self.__class__.__name__, size)

    size = size or io.DEFAULT_BUFFER_SIZE
    return os.read(self.fd, size)

  def _raw_write_stream(self, data):
    self.DEBUG('%s._raw_write_stream: data="%s", len=%s, type=%s', self.__class__.__name__, data, len(data), type(data))

    remaining_chars = len(data)

    while remaining_chars > 0:
      try:
        self.stream.write(data)
        return

      except io.BlockingIOError as e:
        remaining_chars -= e.characters_written
        continue

      except EnvironmentError as e:
        # Resource temporarily unavailable
        if e.errno == 11:
          continue

        raise e

  def _raw_write_fd(self, data):
    self.DEBUG('%s._raw_write_fd: data="%s", len=%s, type=%s', self.__class__.__name__, data, len(data), type(data))

    os.write(self.fd, data)

  @abc.abstractmethod
  def read(self, size = None):
    """
    Read data from stream.

    :param int size: if set, read at maximum ``size`` bytes.
    :rtype: ``bytearray`` (Python2), ``bytes`` (Python3)
    :returns: read data, of maximum lenght of ``size``, ``None`` when there are
      no available data, or empty string in case of EOF.
    """

    raise NotImplementedError('%s does not implement read method' % self.__class__.__name__)

  @abc.abstractmethod
  def write(self, buff):
    """
    Write data to stream.

    :param bytearray buff: data to write. ``bytearray`` (Python2), ``bytes`` (Python3)
    """

    raise NotImplementedError('%s does not implement write method' % self.__class__.__name__)

  def close(self):
    """
    This method will close the stream. If ``allow_close`` flag is not set
    to ``True``, nothing will happen. If the stream wasn't created with ``close``
    set to ``True``, nothing will happen. If the wrapped IO resource does not
    have ``close()`` method, nothing will happen.
    """

    self.DEBUG('%s.close: allow_close=%s, _close=%s', self.__class__.__name__, self.allow_close, self._close)

    if not self.allow_close:
      self.DEBUG('%s.close: not allowed', self.__class__.__name__)
      return

    if self._close is not None:
      self._close()

class InputStream(Stream):
  if PY2:
    def read(self, size = None):
      self.DEBUG('%s.read: size=%s', self.__class__.__name__, size)

      buff = self._raw_read(size = size)
      if not buff:
        return bytearray([])

      return bytearray([ord(c) for c in buff])

  else:
    def read(self, size = None):
      self.DEBUG('%s.read: size=%s', self.__class__.__name__, size)

      buff = self._raw_read(size = size)

      return buff

  def write(self, b):
    raise NotImplementedError('%s does not implement write method' % self.__class__.__name__)

  @staticmethod
  def create(machine, desc):
    machine.LOGGER.debug('InputStream.create: desc=%s', desc)

    if isfile(desc):
      return FileInputStream(machine, desc)

    if hasattr(desc, 'read'):
      return MethodInputStream(machine, desc)

    if hasattr(desc, 'fileno'):
      return FDInputStream(machine, desc.fileno())

    if isinstance(desc, integer_types):
      return FDInputStream(machine, desc)

    if desc == '<stdin>':
      return StdinStream(machine)

    if isinstance(desc, string_types):
      return FileInputStream(machine, open(desc, 'rb'))

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)

class FileInputStream(InputStream):
  def __init__(self, machine, f, **kwargs):
    super(FileInputStream, self).__init__(machine, '<file %s>' % f.name, stream = f, fd = f.fileno())

class MethodInputStream(InputStream):
  def __init__(self, machine, desc, **kwargs):
    super(MethodInputStream, self).__init__(machine, repr(desc), stream = desc)

class FDInputStream(InputStream):
  def __init__(self, machine, fd, **kwargs):
    super(FDInputStream, self).__init__(machine, '<fd %s>' % fd, fd = fd)

class StdinStream(InputStream):
  def __init__(self, machine, **kwargs):
    DEBUG = machine.LOGGER.debug

    self.old_termios = None

    stream = machine.stdin.buffer if hasattr(machine.stdin, 'buffer') else machine.stdin
    fd = machine.stdin.fileno() if hasattr(machine.stdin, 'fileno') else None

    if fd is not None:
      DEBUG('%s.__init__: re-pack <stdin> fd as a new stream to avoid colisions', self.__class__.__name__)

      stream = os.fdopen(fd, 'rb', 0)
      fd = stream.fileno()

      DEBUG('%s.__init__: set <stdin> fd to non-blocking mode', self.__class__.__name__)

      fd_blocking(fd, block = False)

      try:
        self.old_termios = termios.tcgetattr(fd)
        tty.setcbreak(fd)

      except termios.error as e:
        if e.args[0] != errno.ENOTTY:
          raise e

      DEBUG('%s.__init__: stream=%r, fd=%r', self.__class__.__name__, stream, fd)

    super(StdinStream, self).__init__(machine, '<stdin>', stream = stream, fd = fd, close = False, **kwargs)

  def close(self):
    self.DEBUG('%s.close', self.__class__.__name__)

    if self.old_termios is not None:
      termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_termios)

  def get_selectee(self):
    return self.stream

class OutputStream(Stream):
  def read(self, size = None):
    raise NotImplementedError('%s does not implement read method' % self.__class__.__name__)

  if PY2:
    def write(self, buff):
      self.DEBUG('%s.write: buff=%s', self.__class__.__name__, buff)

      self._raw_write(''.join([chr(b) for b in buff]))

  else:
    def write(self, buff):
      self.DEBUG('%s.write: buff=%s', self.__class__.__name__, buff)

      self._raw_write(bytes(buff))

  def flush(self):
    if self.stream is not None and hasattr(self.stream, 'flush'):
      self.stream.flush()

  @staticmethod
  def create(machine, desc):
    machine.LOGGER.debug('OutputStream.create: desc=%s', desc)

    if isfile(desc):
      return FileOutputStream(machine, desc)

    if hasattr(desc, 'write'):
      return MethodOutputStream(machine, desc)

    if hasattr(desc, 'fileno'):
      return FDOutputStream(machine, desc.fileno())

    if isinstance(desc, integer_types):
      return FDOutputStream(machine, desc)

    if desc == '<stdout>':
      return StdoutStream(machine)

    if desc == '<stderr>':
      return StderrStream(machine)

    if isinstance(desc, string_types):
      return FileOutputStream(machine, open(desc, 'wb'))

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)

class FileOutputStream(OutputStream):
  def __init__(self, machine, f, **kwargs):
    super(FileOutputStream, self).__init__(machine, '<file %s>' % f.name, stream = f, fd = f.fileno())

class FDOutputStream(OutputStream):
  def __init__(self, machine, fd, **kwargs):
    super(FDOutputStream, self).__init__(machine, '<fd %s>' % fd, fd = fd)

class MethodOutputStream(OutputStream):
  def __init__(self, machine, desc, **kwargs):
    super(MethodOutputStream, self).__init__(machine, repr(desc), stream = desc)

class StdoutStream(OutputStream):
  def __init__(self, machine):
    stream = machine.stdout.buffer if hasattr(machine.stdout, 'buffer') else machine.stdout
    fd = machine.stdout.fileno() if hasattr(machine.stdout, 'fileno') else None

    super(StdoutStream, self).__init__(machine, '<stdout>', stream = stream, fd = fd, close = False)

class StderrStream(OutputStream):
  def __init__(self, machine):
    stream = machine.stderr.buffer if hasattr(machine.stderr, 'buffer') else machine.stderr
    fd = machine.stderr.fileno() if hasattr(machine.stderr, 'fileno') else None

    super(StderrStream, self).__init__(machine, '<stderr>', stream = stream, fd = fd, close = False)
