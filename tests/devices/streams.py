import sys
import logging

import ducky.errors
import ducky.streams
import ducky.tools
from ducky.errors import InvalidResourceError

from .. import get_tempfile, assert_raises, mock
from functools import partial

LOGGER = logging.getLogger()

def setup_machine():
  M = mock.Mock()
  M.LOGGER = LOGGER

  for stream in ('stdout', 'stderr', 'stdin'):
    setattr(M, stream, getattr(sys, stream))

  return M, partial(ducky.streams.InputStream.create, M), partial(ducky.streams.OutputStream.create, M)

def test_no_stream():
  M, create_input, create_output = setup_machine()

  assert_raises(lambda: create_input(object()), InvalidResourceError)

def test_no_file():
  M, create_input, create_output = setup_machine()

  assert_raises(lambda: create_input('dummy stream description'), IOError)

def test_file():
  with get_tempfile(keep = False) as f:
    M, create_input, create_output = setup_machine()
    g = open(f.name, 'rb')

    s = create_input(g)

    assert s.desc == '<file %s>' % f.name
    assert s.stream == g
    assert s.fd == g.fileno()
    assert s.close == g.close
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = create_output(g)

    assert s.desc == '<file %s>' % f.name
    assert s.stream == g
    assert s.fd == g.fileno()
    assert s.close == g.close
    assert s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_method_proxy():
  M, create_input, create_output = setup_machine()

  with get_tempfile(keep = False) as f:
    class Proxy(object):
      def __init__(self):
        self.read = f.read
        self.write = f.write

    proxy = Proxy()

    s = create_input(proxy)

    assert s.desc == repr(proxy)
    assert s.stream == proxy
    assert s.fd is None
    assert not s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = create_output(proxy)

    assert s.desc == repr(proxy)
    assert s.stream == proxy
    assert s.fd is None
    assert not s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_fileno_proxy():
  M, create_input, create_output = setup_machine()

  with get_tempfile(keep = False) as f:
    class Proxy(object):
      def __init__(self):
        self.fileno = f.fileno

    proxy = Proxy()

    s = create_input(proxy)

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.has_fd()
    assert s._raw_read == s._raw_read_fd
    assert s.get_selectee() == s.fd

    s = create_output(proxy)

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.has_fd()
    assert s._raw_write == s._raw_write_fd
    assert s.get_selectee() == s.fd

def test_fd():
  M, create_input, create_output = setup_machine()

  with get_tempfile(keep = False) as f:
    s = create_input(f.fileno())

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.has_fd()
    assert s._raw_read == s._raw_read_fd
    assert s.get_selectee() == s.fd

    s = create_output(f.fileno())

    assert s.desc == '<fd %s>' % f.fileno()
    assert s.stream is None
    assert s.fd == f.fileno()
    assert s.has_fd()
    assert s._raw_write == s._raw_write_fd
    assert s.get_selectee() == s.fd

def test_path():
  M, create_input, create_output = setup_machine()

  with get_tempfile(keep = False) as f:
    s = create_input(f.name)

    assert s.desc == '<file %s>' % f.name
    assert s.stream.name == f.name
    assert s.fd == s.stream.fileno()
    assert s.close == s.stream.close
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.fd

    s = create_output(f.name)

    assert s.desc == '<file %s>' % f.name
    assert s.stream.name == f.name
    assert s.fd == s.stream.fileno()
    assert s.close == s.stream.close
    assert s.has_fd()
    assert s._raw_write == s._raw_write_stream
    assert s.get_selectee() == s.fd

def test_stdin():
  M, create_input, create_output = setup_machine()

  s = create_input('<stdin>')

  try:
    assert s.desc == '<stdin>'
    assert s.fd == sys.stdin.fileno()
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream
    assert s.get_selectee() == s.stream

  finally:
    s.close()

def test_stdout():
  M, create_input, create_output = setup_machine()

  s = create_output('<stdout>')

  assert s.desc == '<stdout>'
  assert s.stream == sys.stdout
  assert s.fd is (sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else None)
  assert s._raw_write == s._raw_write_stream
  assert s.get_selectee() == s.fd

def test_stderr():
  M, create_input, create_output = setup_machine()

  s = create_output('<stderr>')

  assert s.desc == '<stderr>'
  assert s.stream == sys.stderr
  assert s.fd is (sys.stderr.fileno() if hasattr(sys.stderr, 'fileno') else None)
  assert s._raw_write == s._raw_write_stream
  assert s.get_selectee() == s.fd

def test_unknown():
  M, create_input, create_output = setup_machine()

  class Proxy(object):
    pass

  proxy = Proxy()

  assert_raises(lambda: create_input(proxy), InvalidResourceError)
  assert_raises(lambda: create_output(proxy), InvalidResourceError)
