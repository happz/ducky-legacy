"""
Streams represent basic IO objects, used by devices for reading or writing
streams of data.

``Stream`` object encapsulates an actual IO object - either ``file``-like
stream, or raw file descriptor. ``Stream`` then provides basic IO methods
for accessing content of IO object, shielding user from Python2/Python3
and ``file``/descriptor differencies.
"""

import abc
import io
import os
import sys

from six import PY2, integer_types, string_types, add_metaclass

from .errors import InvalidResourceError
from .util import isfile

@add_metaclass(abc.ABCMeta)
class Stream(object):
  """
  Abstract base class of all streams.

  :param logger: logger object used for logging.
  :param desc: description of stream. This is a short, string representation
    of the stream.
  :param stream: ``file``-like stream that provides IO method (``read()`` or
    ``write``). If it is set, it is preferred IO object.
  :param int fd: raw file descriptor. ``stream`` takes precedence, otherwise this
    file descriptor is used.
  :param bool close: if ``True``, and if ``stream`` has a ``close()`` method, stream
    will provide ``close()`` method that will close the underlaying ``file``-like
    object.
  """

  def __init__(self, logger, desc, stream = None, fd = None, close = True):
    if stream is None and fd is None:
      raise InvalidResourceError('Stream "%s" must have stream object or raw file descriptor.' % desc)

    self.logger = logger
    self.DEBUG = logger.debug
    self.DEBUG = logger.info

    self.desc = desc
    self.stream = stream
    self.fd = fd

    self._raw_read = self._raw_read_stream if stream is not None else self._raw_read_fd
    self._raw_write = self._raw_write_stream if stream is not None else self._raw_write_fd

    self.close = stream.close if close and stream is not None and hasattr(stream, 'close') else self._close_dummy

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

    self.stream.write(data)

  def _raw_write_fd(self, data):
    self.DEBUG('%s._raw_write_fd: data="%s", len=%s, type=%s', self.__class__.__name__, data, len(data), type(data))

    os.write(self.fd, data)

  @abc.abstractmethod
  def read(self, size = None):
    """
    Read data from stream.

    :param int size: if set, read at maximum ``size`` bytes.
    :rtype: ``bytearray`` (Python2), ``bytes`` (Python3)
    :returns: read data, of maximum lenght of ``size``.
    """

    raise NotImplementedError('%s does not implement read method' % self.__class__.__name__)

  @abc.abstractmethod
  def write(self, buff):
    """
    Write data to stream.

    :param bytearray buff: data to write. ``bytearray`` (Python2), ``bytes`` (Python3)
    """

    raise NotImplementedError('%s does not implement write method' % self.__class__.__name__)

  def _close_dummy(self):
    """
    Dummy close method, used when stream is not expected to close underlying IO object.
    """

    self.DEBUG('%s.close: not supported', self.__class__.__name__)
    pass

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
  def create(logger, desc):
    logger.debug('InputStream.create: desc=%s', desc)

    if isfile(desc):
      return FileInputStream(logger, desc)

    if hasattr(desc, 'read'):
      return MethodInputStream(logger, desc)

    if hasattr(desc, 'fileno'):
      return FDInputStream(logger, desc.fileno())

    if isinstance(desc, integer_types):
      return FDInputStream(logger, desc)

    if desc == '<stdin>':
      return StdinStream(logger)

    if isinstance(desc, string_types):
      return FileInputStream(logger, open(desc, 'rb'))

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)

class FileInputStream(InputStream):
  def __init__(self, logger, f, **kwargs):
    super(FileInputStream, self).__init__(logger, '<file %s>' % f.name, stream = f, fd = f.fileno())

class MethodInputStream(InputStream):
  def __init__(self, logger, desc, **kwargs):
    super(MethodInputStream, self).__init__(logger, repr(desc), stream = desc)

class FDInputStream(InputStream):
  def __init__(self, logger, fd, **kwargs):
    super(FDInputStream, self).__init__(logger, '<fd %s>' % fd, fd = fd)

class StdinStream(InputStream):
  def __init__(self, logger, **kwargs):
    stream = sys.stdin.buffer if hasattr(sys.stdin, 'buffer') else sys.stdin
    fd = sys.stdin.fileno() if hasattr(sys.stdin, 'fileno') else None

    super(StdinStream, self).__init__(logger, '<stdin>', stream = stream, fd = fd, close = False, **kwargs)

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

  @staticmethod
  def create(logger, desc):
    logger.debug('OutputStream.create: desc=%s', desc)

    if isfile(desc):
      return FileOutputStream(logger, desc)

    if hasattr(desc, 'write'):
      return MethodOutputStream(logger, desc)

    if hasattr(desc, 'fileno'):
      return FDOutputStream(logger, desc.fileno())

    if isinstance(desc, integer_types):
      return FDOutputStream(logger, desc)

    if desc == '<stdout>':
      return StdoutStream(logger)

    if desc == '<stderr>':
      return StderrStream(logger)

    if isinstance(desc, string_types):
      return FileOutputStream(logger, open(desc, 'wb'))

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)

class FileOutputStream(OutputStream):
  def __init__(self, logger, f, **kwargs):
    super(FileOutputStream, self).__init__(logger, '<file %s>' % f.name, stream = f, fd = f.fileno())

class FDOutputStream(OutputStream):
  def __init__(self, logger, fd, **kwargs):
    super(FDOutputStream, self).__init__(logger, '<fd %s>' % fd, fd = fd)

class MethodOutputStream(OutputStream):
  def __init__(self, logger, desc, **kwargs):
    super(MethodOutputStream, self).__init__(logger, repr(desc), stream = desc)

class StdoutStream(OutputStream):
  def __init__(self, logger):
    stream = sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else sys.stdout
    fd = sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else None

    super(StdoutStream, self).__init__(logger, '<stdout>', stream = stream, fd = fd, close = False)

class StderrStream(OutputStream):
  def __init__(self, logger):
    stream = sys.stderr.buffer if hasattr(sys.stderr, 'buffer') else sys.stderr
    fd = sys.stderr.fileno() if hasattr(sys.stderr, 'fileno') else None

    super(StderrStream, self).__init__(logger, '<stderr>', stream = stream, fd = fd, close = False)
