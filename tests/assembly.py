import string

from ducky.asm import AssemblerProcess
from ducky.asm.lexer import reserved_map

from . import LOGGER

from hypothesis import given, assume
from hypothesis.strategies import integers, text

def translate_buffer(code):
  LOGGER.debug('translate code:')
  LOGGER.debug(code)
  LOGGER.debug('~~~~~')

  process = AssemblerProcess('test.S', logger = LOGGER)
  process.preprocessed = code

  process.parse()

def assert_exc(code, exc_class, column = None, filename = None, length = None, line = None, lineno = None, message = None, text = None):
  LOGGER.debug('TEST: exc_class=%s', exc_class.__name__ if exc_class is not None else 'None')
  LOGGER.debug('  column=%s, filename=%s, length=%s, line="%s", lineno=%s, message"%s", text="%s"',
               column, filename, length, line, lineno, message, text)

  if exc_class is None:
    translate_buffer(code)

  else:
    try:
      translate_buffer(code)

    except exc_class as exc:
      LOGGER.debug('~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
      for l in exc.text:
        LOGGER.debug(l)
      LOGGER.debug('~~~~~~~~~~~~~~~~~~~~~~~~~~~~')

      assert exc.location.column == column, 'Column: expected %s, found %s' % (column, exc.location.column)
      assert exc.location.filename == filename
      assert exc.location.length == length
      assert exc.line == line
      assert exc.location.lineno == lineno
      assert exc.message == message, exc.message
      assert exc.text == text, exc.text

    except Exception as exc:
      assert False, 'Unexpected exception raised: %r' % exc

    else:
      assert False, 'No exception raised'


def __do_test_integer_dec(directive, i):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, i=%d', directive, i)

  translate_buffer('  %s  %d  ' % (directive, i))

def __do_test_integer_hex(directive, i):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, i=%d', directive, i)

  translate_buffer('  %s  0x%x  ' % (directive, i))

def __do_test_integer_name(directive, name):
  assume(not name[0].isdigit())
  assume(name not in reserved_map)

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, name=%s', directive, name)

  translate_buffer('  %s  %s  ' % (directive, name))

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_byte_dec(i):
  __do_test_integer_dec('.byte', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_word_dec(i):
  __do_test_integer_dec('.word', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_short_dec(i):
  __do_test_integer_dec('.short', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_byte_hex(i):
  __do_test_integer_hex('.byte', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_word_hex(i):
  __do_test_integer_hex('.word', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_short_hex(i):
  __do_test_integer_hex('.short', i)

@given(name = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_byte_id(name):
  __do_test_integer_name('.byte', name)

@given(name = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_word_id(name):
  __do_test_integer_name('.word', name)

@given(name = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_short_id(name):
  __do_test_integer_name('.short', name)

# def test_byte_var():
#  translate_buffer('  .set %foo, 1\n  .byte %foo  ; foo ')
#
# def test_word_var():
#  translate_buffer('  .set %foo, 1\n  .word %foo  ; foo ')
#
# def test_short_var():
#  translate_buffer('  .set %foo, 1\n  .short %foo  ; foo ')
