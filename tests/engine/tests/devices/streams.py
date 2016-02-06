import sys

import ducky.errors
import ducky.streams
import ducky.tools

from .. import TestCase, get_tempfile

class Tests(TestCase):
  logger = ducky.tools.setup_logger()

  def test_no_stream(self):
    with self.assertRaises(ducky.errors.InvalidResourceError):
      ducky.streams.InputStream(Tests.logger, 'dummy stream description')

  def test_file(self):
    with get_tempfile(keep = False) as f:
      g = open(f.name, 'rb')
      s = ducky.streams.InputStream.create(Tests.logger, g)

      assert s.desc == '<file %s>' % f.name
      assert s.stream == g
      assert s.fd == g.fileno()
      assert s.close == g.close
      assert s.has_fd()
      assert s._raw_read == s._raw_read_stream

      s = ducky.streams.OutputStream.create(Tests.logger, g)

      assert s.desc == '<file %s>' % f.name
      assert s.stream == g
      assert s.fd == g.fileno()
      assert s.close == g.close
      assert s.has_fd()
      assert s._raw_write == s._raw_write_stream

  def test_method_proxy(self):
    with get_tempfile(keep = False) as f:
      class Proxy(object):
        def __init__(self):
          self.read = f.read
          self.write = f.write

      proxy = Proxy()

      s = ducky.streams.InputStream.create(Tests.logger, proxy)

      assert s.desc == repr(proxy)
      assert s.stream == proxy
      assert s.fd is None
      assert s.close == s._close_dummy
      assert not s.has_fd()
      assert s._raw_read == s._raw_read_stream

      s = ducky.streams.OutputStream.create(Tests.logger, proxy)

      assert s.desc == repr(proxy)
      assert s.stream == proxy
      assert s.fd is None
      assert s.close == s._close_dummy
      assert not s.has_fd()
      assert s._raw_write == s._raw_write_stream

  def test_fileno_proxy(self):
    with get_tempfile(keep = False) as f:
      class Proxy(object):
        def __init__(self):
          self.fileno = f.fileno

      proxy = Proxy()

      s = ducky.streams.InputStream.create(Tests.logger, proxy)

      assert s.desc == '<fd %s>' % f.fileno()
      assert s.stream is None
      assert s.fd == f.fileno()
      assert s.close == s._close_dummy
      assert s.has_fd()
      assert s._raw_read == s._raw_read_fd

      s = ducky.streams.OutputStream.create(Tests.logger, proxy)

      assert s.desc == '<fd %s>' % f.fileno()
      assert s.stream is None
      assert s.fd == f.fileno()
      assert s.close == s._close_dummy
      assert s.has_fd()
      assert s._raw_write == s._raw_write_fd

  def test_fd(self):
    with get_tempfile(keep = False) as f:
      s = ducky.streams.InputStream.create(Tests.logger, f.fileno())

      assert s.desc == '<fd %s>' % f.fileno()
      assert s.stream is None
      assert s.fd == f.fileno()
      assert s.close == s._close_dummy
      assert s.has_fd()
      assert s._raw_read == s._raw_read_fd

      s = ducky.streams.OutputStream.create(Tests.logger, f.fileno())

      assert s.desc == '<fd %s>' % f.fileno()
      assert s.stream is None
      assert s.fd == f.fileno()
      assert s.close == s._close_dummy
      assert s.has_fd()
      assert s._raw_write == s._raw_write_fd

  def test_path(self):
    with get_tempfile(keep = False) as f:
      s = ducky.streams.InputStream.create(Tests.logger, f.name)

      assert s.desc == '<file %s>' % f.name
      assert s.stream.name == f.name
      assert s.fd == s.stream.fileno()
      assert s.close == s.stream.close
      assert s.has_fd()
      assert s._raw_read == s._raw_read_stream

      s = ducky.streams.OutputStream.create(Tests.logger, f.name)

      assert s.desc == '<file %s>' % f.name
      assert s.stream.name == f.name
      assert s.fd == s.stream.fileno()
      assert s.close == s.stream.close
      assert s.has_fd()
      assert s._raw_write == s._raw_write_stream

  def test_stdin(self):
    s = ducky.streams.InputStream.create(Tests.logger, '<stdin>')

    assert s.desc == '<stdin>'
    assert s.fd == sys.stdin.fileno()
    assert s.close == s._close_dummy
    assert s.has_fd()
    assert s._raw_read == s._raw_read_stream

  def test_stdout(self):
    s = ducky.streams.OutputStream.create(Tests.logger, '<stdout>')

    assert s.desc == '<stdout>'
    assert s.stream == sys.stdout
    assert s.fd is (sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else None)
    assert s.close == s._close_dummy
    assert s._raw_write == s._raw_write_stream

  def test_stderr(self):
    s = ducky.streams.OutputStream.create(Tests.logger, '<stderr>')

    assert s.desc == '<stderr>'
    assert s.stream == sys.stderr
    assert s.fd is (sys.stderr.fileno() if hasattr(sys.stderr, 'fileno') else None)
    assert s.close == s._close_dummy
    assert s._raw_write == s._raw_write_stream

  def test_unknown(self):
    class Proxy(object):
      pass

    proxy = Proxy()

    with self.assertRaises(ducky.errors.InvalidResourceError):
      ducky.streams.InputStream.create(Tests.logger, proxy)

    with self.assertRaises(ducky.errors.InvalidResourceError):
      ducky.streams.OutputStream.create(Tests.logger, proxy)
