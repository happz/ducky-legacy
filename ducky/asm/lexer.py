import ply.lex

#
# Lexer setup
#
instructions = (
  'NOP', 'INT', 'IPI', 'RETINT', 'CALL', 'RET', 'CLI', 'STI', 'HLT', 'RST', 'IDLE',
  'PUSH', 'POP', 'INC', 'DEC', 'ADD', 'SUB', 'CMP', 'J', 'AND', 'OR', 'XOR', 'NOT',
  'SHL', 'SHR', 'SHRS', 'LW', 'LS', 'LB', 'LI', 'LIU', 'LA', 'STW', 'STS', 'STB',
  'MOV', 'SWP', 'MUL', 'UDIV', 'MOD', 'CMPU', 'CAS', 'SIS', 'DIV',
  'BE', 'BNE', 'BS', 'BNS', 'BZ', 'BNZ', 'BO', 'BNO', "BL", "BLE", "BGE", "BG",
  'SETE', 'SETNE', 'SETZ', 'SETNZ', 'SETO', 'SETNO', 'SETS', 'SETNS', "SETL", "SETLE", "SETGE", "SETG",
  'SELE', 'SELNE', 'SELZ', 'SELNZ', 'SELS', 'SELNS', 'SELO', 'SELNO', "SELL", "SELLE", "SELGE", "SELG",
  'LPM', 'CTR', 'CTW', 'FPTC'
)

math_instructions = (
  'PUSHW', 'SAVEW', 'POPW', 'LOADW', 'POPUW', 'LOADUW', 'SAVE', 'LOAD',
  'INCL', 'DECL', 'ADDL', 'MULL', 'DIVL', 'MODL', 'UDIVL', 'UMODL',
  'DUP', 'DUP2', 'SWPL', 'DROP', 'SYMDIVL', 'SYMMODL',
  'PUSHL', 'POPL'
)

directives = (
  'data', 'text',
  'type', 'global',
  'ascii', 'byte', 'short', 'space', 'string', 'word',
  'section',
  'align', 'file',
  'set'
)

# Construct list of tokens, and map of reserved words
tokens = instructions + math_instructions + (
  'COMMA', 'COLON', 'HASH', 'LBRAC', 'RBRAC', 'DOT',
  'SCONST', 'ICONST',
  'ID', 'REGISTER'
)

reserved_map = {
  # Special registers
  'sp':     'REGISTER',
  'fp':     'REGISTER',

  # Special instructions
  'shiftl': 'SHL',
  'shiftr': 'SHR',
  'shiftrs': 'SHRS'
}

reserved_map.update({i.lower(): i for i in instructions})
reserved_map.update({i.lower(): i for i in math_instructions})

tokens = tokens + tuple([i.upper() for i in directives])
reserved_map.update({'.' + i: i.upper() for i in directives})
reserved_map.update({i: i.upper() for i in directives})

reserved_map.update({'r%d' % i: 'REGISTER' for i in range(0, 32)})

# Newlines
def t_NEWLINE(t):
  r'\n+'

  t.lexer.lineno += t.value.count('\n')

# Tokens
t_COMMA          = r','
t_COLON          = r':'
t_HASH           = r'\#'
t_LBRAC = r'\['
t_RBRAC = r'\]'
t_DOT   = r'\.'

t_SCONST = r'\"([^\\\n]|(\\.))*?\"'
t_ICONST = r'[+-]?(?:(?:0x[0-9a-fA-F][0-9a-fA-F]*)|(?:[0-9][0-9]*))'

def t_ID(t):
  r'[a-zA-Z_\.][a-zA-Z0-9_\.]*'

  t.type = reserved_map.get(t.value, 'ID')
  return t

t_ignore = " \t"

def t_error(t):
  from ..errors import AssemblyIllegalCharError

  loc = t.lexer.location.copy()
  loc.lineno = t.lineno - loc.lineno
  loc.column = t.lexer.parser.lexpos_to_lineno(t.lexpos)

  raise AssemblyIllegalCharError(c = t.value[0], location = loc, line = t.lexer.parser.lineno_to_line(t.lineno))

class AssemblyLexer(object):
  def __init__(self):
    self._lexer = ply.lex.lex()

  def token(self, *args, **kwargs):
    return self._lexer.token(*args, **kwargs)

  def input(self, *args, **kwargs):
    return self._lexer.input(*args, **kwargs)
