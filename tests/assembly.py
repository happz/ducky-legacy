import string

from ducky.cpu.assemble import translate_buffer as orig_translate_buffer, RE_INTEGER
from ducky.errors import IncompleteDirectiveError, UnalignedJumpTargetError

from . import LOGGER

from functools import partial
from hypothesis import given, assume
from hypothesis.strategies import integers, sampled_from, text

translate_buffer = partial(orig_translate_buffer, LOGGER)

def assert_exc(code, exc_class, column = None, filename = None, length = None, line = None, lineno = None, message = None, text = None):
  LOGGER.debug('TEST: code="%s", exc_class=%s', code, exc_class.__name__ if exc_class is not None else 'None')
  LOGGER.debug('  column=%s, filename=%s, length=%s, line="%s", lineno=%s, message"%s", text="%s"',
               column, filename, length, line, lineno, message, text)

  translate = partial(translate_buffer, code, filename = 'test.S')

  if exc_class is None:
    translate()

  else:
    try:
      translate()

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


@given(base = sampled_from([10, 16]), immediate = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_parse_immediate_integer(base, immediate):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: base=%d, immediate=%d', base, immediate)

  immediate_string = ('%d' % immediate) if base == 10 else ('0x%X' % immediate)
  pattern = ' %s ' % immediate_string
  LOGGER.debug('  pattern="%s"', pattern)

  m = RE_INTEGER.match(pattern)
  assert m is not None

  m = m.groupdict()
  LOGGER.debug('  matches=%s', m)

  assert m['value_hex'] == (None if base == 10 else immediate_string)
  assert m['value_label'] is None
  assert m['value_var'] is None
  assert m['value_dec'] == (immediate_string if base == 10 else None)

@given(immediate = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_'))
def test_parse_immediate_variable(immediate):
  immediate = immediate.encode('ascii', 'replace')

  assume(not immediate[0].isdigit())
  assume(immediate[0] != '_')

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: immediate="%s"', immediate)

  pattern = ' %s ' % immediate
  LOGGER.debug('  pattern="%s"', pattern)

  m = RE_INTEGER.match(pattern)
  assert m is not None

  m = m.groupdict()
  LOGGER.debug('  matches=%s', m)

  assert m['value_hex'] is None
  assert m['value_label'] is None
  assert m['value_var'] == immediate
  assert m['value_dec'] is None

@given(immediate = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_parse_immediate_label(immediate):
  immediate = immediate.encode('ascii', 'replace')

  assume(not immediate[0].isdigit())

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: immediate="%s"', immediate)

  pattern = ' &%s ' % immediate
  LOGGER.debug('  pattern="%s"', pattern)

  m = RE_INTEGER.match(pattern)
  assert m is not None

  m = m.groupdict()
  LOGGER.debug('  matches=%s', m)

  assert m['value_hex'] is None
  assert m['value_label'] == '&' + immediate
  assert m['value_var'] is None
  assert m['value_dec'] is None

def __do_test_integer_dec(directive, i):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, i=%d', directive, i)

  translate_buffer('  %s  %d  ; comment  ' % (directive, i))

def __do_test_integer_hex(directive, i):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, i=%d', directive, i)

  translate_buffer('  %s  0x%x  ; comment  ' % (directive, i))

def __do_test_integer_label(directive, label):
  assume(not label[0].isdigit())

  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: directive=%s, label=%s', directive, label)

  translate_buffer('  %s  &%s  ; comment' % (directive, label))

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_byte_dec(i):
  __do_test_integer_dec('.byte', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_int_dec(i):
  __do_test_integer_dec('.int', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_short_dec(i):
  __do_test_integer_dec('.short', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_byte_hex(i):
  __do_test_integer_hex('.byte', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_int_hex(i):
  __do_test_integer_hex('.int', i)

@given(i = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_short_hex(i):
  __do_test_integer_hex('.short', i)

@given(label = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_byte_label(label):
  __do_test_integer_label('.byte', label)

@given(label = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_int_label(label):
  __do_test_integer_label('.int', label)

@given(label = text(min_size = 1, alphabet = string.ascii_letters + string.digits + '_.'))
def test_short_label(label):
  __do_test_integer_label('.short', label)

def test_byte_var():
  translate_buffer('  .set foo, 1\n  .byte foo  ; foo ')

def test_int_var():
  translate_buffer('  .set foo, 1\n  .int foo  ; foo ')

def test_short_var():
  translate_buffer('  .set foo, 1\n  .short foo  ; foo ')

def test_int_incomplete():
  line = '  .int    ; foo '

  assert_exc(line, IncompleteDirectiveError,
             column = 6,
             filename = 'test.S',
             line = line,
             lineno = 1,
             message = 'test.S:1:6: Incomplete directive: directive without a value specification',
             text = ['test.S:1:6: Incomplete directive: directive without a value specification', line, '      ^'])

def test_int_meaningless():
  line = '  .int 0xFG    ; foo '

  assert_exc(line, IncompleteDirectiveError,
             column = 6,
             filename = 'test.S',
             line = line,
             lineno = 1,
             message = 'test.S:1:6: Incomplete directive: directive without a meaningful value',
             text = ['test.S:1:6: Incomplete directive: directive without a meaningful value', line, '      ^'])

@given(offset = integers(min_value = 0, max_value = 0xFFFFFFFF))
def test_unaligned_jump(offset):
  LOGGER.debug('----- ----- ----- ----- ----- ----- -----')
  LOGGER.debug('TEST: offset=0x%08X', offset)

  code = '  j 0x%X  ; comment ' % offset

  assert_exc(code, None if (offset & 0x3 == 0) else UnalignedJumpTargetError,
             column = None,
             filename = 'test.S',
             line = code,
             lineno = 1,
             message = 'test.S:1: Jump destination address is not 4-byte aligned: address=0x%08X' % offset,
             text = ['test.S:1: Jump destination address is not 4-byte aligned: address=0x%08X' % offset, '  j 0x%X  ; comment ' % offset])
