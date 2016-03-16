import sys
import logging

import ducky.errors
import ducky.streams
import ducky.tools
from ducky.errors import InvalidResourceError

from .. import get_tempfile, assert_raises

LOGGER = logging.getLogger()

def test_no_stream():
  assert_raises(lambda: ducky.streams.InputStream(LOGGER, 'dummy stream description'), InvalidResourceError)

def test_file():
  with get_tempfile(keep = False) as f:
    g = open(f.name, 'rb')
    s = ducky.streams.InputStream.create(LOGGER, g)

    assert s.desc == '<file %s>' % f.name
    assert s.stream == g
    assert s.fd == g.fileno()
    assert s.close == g.close
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = ducky.streams.OutputStream.create(LOGGER, g)

    assert s.desc == '<file %s>' % f.name
    assert s.stream == g
    assert s.fd == g.fileno()
    assert s.close == g.close
    assert s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_method_proxy():
  with get_tempfile(keep = False) as f:
    class Proxy(object):
      def __init__(self):
        self.read = f.read
        self.write = f.write

    proxy = Proxy()

    s = ducky.streams.InputStream.create(LOGGER, proxy)

    assert s.desc == repr(proxy)
    assert s.stream == proxy
    assert s.fd is None
    assert s.close == s._close_dummy
    assert not s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = ducky.streams.OutputStream.create(LOGGER, proxy)

    assert s.desc == repr(proxy)
    assert s.stream == proxy
    assert s.fd is None
    assert s.close == s._close_dummy
    assert not s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_fileno_proxy():
  with get_tempfile(keep = False) as f:
    class Proxy(object):
      def __init__(self):
        self.fileno = f.fileno

    proxy = Proxy()

    s = ducky.streams.InputStream.create(LOGGER, proxy)

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.close == s._close_dummy
    assert s.has_fd()
    assert s._raw_read == s._raw_read_fd
    assert s.get_selectee() == s.fd

    s = ducky.streams.OutputStream.create(LOGGER, proxy)

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.close == s._close_dummy
    assert s.has_fd()
    assert s._raw_write == s._raw_write_fd
    assert s.get_selectee() == s.fd

def test_fd():
  with get_tempfile(keep = False) as f:
    s = ducky.streams.InputStream.create(LOGGER, f.fileno())

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.close == s._close_dummy
    assert s.has_fd()
    assert s._raw_read == s._raw_read_fd
    assert s.get_selectee() == s.fd

    s = ducky.streams.OutputStream.create(LOGGER, f.fileno())

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.close == s._close_dummy
    assert s.has_fd()
    assert s._raw_write == s._raw_write_fd
    assert s.get_selectee() == s.fd

def test_path():
  with get_tempfile(keep = False) as f:
    s = ducky.streams.InputStream.create(LOGGER, f.name)

    assert s.desc == '<file %s>' % f.name
    assert s.stream.name == f.name
    assert s.fd == s.stream.fileno()
    assert s.close == s.stream.close
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = ducky.streams.OutputStream.create(LOGGER, f.name)

    assert s.desc == '<file %s>' % f.name
    assert s.stream.name == f.name
    assert s.fd == s.stream.fileno()
    assert s.close == s.stream.close
    assert s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_stdin():
  s = ducky.streams.InputStream.create(LOGGER, '<stdin>')

  assert s.desc == '<stdin>'
  assert s.fd == sys.stdin.fileno()
  assert s.close == s._close_dummy
  assert s.has_fd()
  assert s._raw_read == s._raw_read_stream
  assert s.get_selectee() == s.stream

def test_stdout():
  s = ducky.streams.OutputStream.create(LOGGER, '<stdout>')

  assert s.desc == '<stdout>'
  assert s.stream == sys.stdout
  assert s.fd is (sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else None)
  assert s.close == s._close_dummy
  assert s._raw_write == s._raw_write_stream
  assert s.get_selectee() == s.fd

def test_stderr():
  s = ducky.streams.OutputStream.create(LOGGER, '<stderr>')

  assert s.desc == '<stderr>'
  assert s.stream == sys.stderr
  assert s.fd is (sys.stderr.fileno() if hasattr(sys.stderr, 'fileno') else None)
  assert s.close == s._close_dummy
  assert s._raw_write == s._raw_write_stream
  assert s.get_selectee() == s.fd

def test_unknown():
  class Proxy(object):
    pass

  proxy = Proxy()

  assert_raises(lambda: ducky.streams.InputStream.create(LOGGER, proxy), InvalidResourceError)
  assert_raises(lambda: ducky.streams.OutputStream.create(LOGGER, proxy), InvalidResourceError)
