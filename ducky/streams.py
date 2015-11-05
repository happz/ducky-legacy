import io
import os
import sys

from six import PY2, integer_types, string_types

from .errors import InvalidResourceError
from .util import isfile, bytes2str

class Stream(object):
  def __init__(self, logger, desc, stream = None, fd = None, close = True):
    self.logger = logger
    self.DEBUG = logger.debug
    self.DEBUG = logger.info

    if stream is None and fd is None:
      raise Exception()

    self.desc = desc
    self.stream = stream
    self.fd = fd

    self._raw_read = self._raw_read_stream if stream is not None else self._raw_read_fd
    self._raw_write = self._raw_write_stream if stream is not None else self._raw_write_fd

    if close and stream is not None and hasattr(stream, 'close'):
      self.close = stream.close

  def __repr__(self):
    return '<%s %s>' % (self.__class__.__name__, self.desc)

  def has_fd(self):
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

  def read_u8(self, size = None):
    raise NotImplementedError('%s does not implement read_u8 method' % self.__class__.__name__)

  def write_u8(self, b):
    raise NotImplementedError('%s does not implement write_u8 method' % self.__class__.__name__)

  def close(self):
    self.DEBUG('%s.close: not supported', self.__class__.__name__)
    pass

class InputStream(Stream):
  def __init__(self, *args, **kwargs):
    super(InputStream, self).__init__(*args, **kwargs)

    self.read_u8 = self._read_u8_py2 if PY2 else self._read_u8_py3

  def _read_u8_py2(self, size = None):
    self.DEBUG('%s._read_u8_py2: size=%s', self.__class__.__name__, size)

    buff = self._raw_read(size = size)
    if not buff:
      return bytearray([])

    return bytearray([ord(c) for c in buff])

  def _read_u8_py3(self, size = None):
    self.DEBUG('%s._read_u8_py3: size=%s', self.__class__.__name__, size)

    buff = self._raw_read(size = size)

    if isinstance(buff, str):
      buff = bytes(buff, 'latin-1')

    return buff

  @staticmethod
  def create(logger, desc):
    logger.debug('InputStream.create: desc=%s', desc)

    if isfile(desc):
      return InputStream(logger, '<file %s>' % desc.name, stream = desc, fd = desc.fileno())

    if hasattr(desc, 'read'):
      return InputStream(logger, repr(desc), stream = desc)

    if hasattr(desc, 'fileno'):
      return InputStream(logger, repr(desc), fd = desc.fileno())

    if isinstance(desc, integer_types):
      return InputStream(logger, '<fd %i>' % desc, fd = desc)

    if desc == '<stdin>':
      return InputStream(logger, '<stdin>', stream = sys.stdin, fd = sys.stdin.fileno(), close = False)

    if isinstance(desc, string_types):
      stream = open(desc, 'r')
      return InputStream(logger, '<file %s>' % stream.name, stream = stream, fd = stream.fileno())

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)

class OutputStream(Stream):
  def __init__(self, *args, **kwargs):
    super(OutputStream, self).__init__(*args, **kwargs)

    self.write_u8 = self._write_u8_py2 if PY2 else self._write_u8_py3

  def _write_u8_py2(self, buff):
    self.DEBUG('%s._write_u8_py2: buff=%s', self.__class__.__name__, buff)

    self._raw_write(''.join([chr(b) for b in buff]))

  def _write_u8_py3(self, buff):
    self.DEBUG('%s._write_u8_py3: buff=%s', self.__class__.__name__, buff)

    self._raw_write(bytes2str(bytes(buff)))

  @staticmethod
  def create(logger, desc):
    logger.debug('OutputStream.create: desc=%s', desc)

    if isfile(desc):
      return OutputStream(logger, desc = '<file %s>' % desc.name, stream = desc, fd = desc.fileno())

    if hasattr(desc, 'write'):
      return OutputStream(logger, repr(desc), stream = desc)

    if hasattr(desc, 'fileno'):
      return OutputStream(logger, repr(desc), fd = desc.fileno())

    if isinstance(desc, integer_types):
      return OutputStream(logger, '<fd %i>' % desc, fd = desc)

    if desc == '<stdout>':
      return OutputStream(logger, '<stdout>', stream = sys.stdout, fd = sys.stderr.fileno(), close = False)

    if desc == '<stderr>':
      return OutputStream(logger, '<stderr>', stream = sys.stderr, fd = sys.stderr.fileno(), close = False)

    if isinstance(desc, string_types):
      stream = open(desc, 'w')
      return OutputStream(logger, '<file %s>' % stream.name, stream = stream, fd = stream.fileno())

    raise InvalidResourceError('Unknown stream description: desc=%s' % desc)
