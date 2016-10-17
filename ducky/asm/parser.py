import ply.yacc

from .lexer import tokens  # NOQA
from .ast import LabelNode, GlobalDirectiveNode, FileDirectiveNode, SectionDirectiveNode, DataSectionDirectiveNode, TextSectionDirectiveNode, SetDirectiveNode
from .ast import StringNode, AsciiNode, SpaceNode, AlignNode, ByteNode, ShortNode, WordNode, InstructionNode, ExpressionNode
from .ast import SourceLocation
from .ast import RegisterOperand, ImmediateOperand, ReferenceOperand, BOOperand
from ..util import str2int

def push_files_stack(p, filepath, offset):
  p.parser.location.filename = filepath[1:-1]
  p.parser.location.lineno = offset

def pop_files_stack(p, filepath, offset):
  p.parser.location.filename = filepath[1:-1]
  p.parser.location.lineno = offset + 1


def get_ast_node(p, klass, *args, **kwargs):
  _loc = p.parser.location
  kwargs['location'] = SourceLocation(filename = _loc.filename, lineno = p.lineno(0) - _loc.lineno)

  return klass(*args, **kwargs)

def append_ast_node(p, klass, *args, **kwargs):
  node = get_ast_node(p, klass, *args, **kwargs)
  p[0] = node

  p.parser.root.children.append(node)

def p_translation_unit(p):
  'translation_unit : statement_list'
  pass

def p_statement_list_1(p):
  'statement_list : statement'
  pass

def p_statement_list_2(p):
  'statement_list : statement_list statement'
  pass

def p_statement(p):
  '''statement : directive
               | label
               | slot-definition
               | linemarker
               | instruction
               '''
  p[0] = p[1]

# Numbers
def p_number(p):
  'number : ICONST'

  p[0] = str2int(p[1])

# Right-hand expressions - these can be assigned to slots (e.g. `.word <expr>`)
def p_expression_term(p):
  '''expr-term : number
               | ID
               | DOT
               '''

  p[0] = get_ast_node(p, ExpressionNode, p[1])

def p_expression_plus(p):
  '''expr-plus : expr-term PLUS expr-term'''

  p[0] = get_ast_node(p, ExpressionNode, (p[1], '+', p[3]))

def p_expr(p):
  '''expression : expr-term
                | expr-plus
                '''
  p[0] = p[1]

# Preprocesor linemarkers
def p_linemarker_flags_1(p):
  'linemarker-flags : number'
  p[0] = p[1]

def p_linemarker_flags_2(p):
  'linemarker-flags : linemarker-flags number'
  p[0] = p[1] + p[2]

def p_linemarker_1(p):
  'linemarker : HASH number SCONST linemarker-flags'

  filename = p[3]
  lineno = p[2]
  flag = p[4]

  if flag not in (1, 2):
    return

  if flag == 1:
    push_files_stack(p, filename, 0)

  elif flag == 2:
    pop_files_stack(p, filename, p.lineno(1) - lineno)

def p_linemarker_2(p):
  'linemarker : HASH number SCONST'

  filename = p[3]
  lineno = p[2]

  push_files_stack(p, filename, p.lineno(1) - lineno + 1)

# Assembler directives
def p_directive(p):
  '''directive         : section-directive
                       | global-directive
                       | align-directive
                       | file-directive
                       | set-directive
     section-directive : data-section
                       | text-section
                       | section
                       '''
  pass

def p_align_directive(p):
  'align-directive : ALIGN expression'

  append_ast_node(p, AlignNode, p[2])

def p_file_directive(p):
  'file-directive : FILE SCONST'

  append_ast_node(p, FileDirectiveNode, p[2][1:-1])

def p_global_directive(p):
  'global-directive : GLOBAL ID'

  append_ast_node(p, GlobalDirectiveNode, p[2])

def p_section_directive(p):
  '''section : SECTION ID
             | SECTION ID COMMA SCONST
             | SECTION DATA
             | SECTION DATA COMMA SCONST
             | SECTION TEXT
             | SECTION TEXT COMMA SCONST
             '''

  if len(p) == 3:
    append_ast_node(p, SectionDirectiveNode, p[2], None)

  else:
    append_ast_node(p, SectionDirectiveNode, p[2], p[4][1:-1])

def p_data_section(p):
  'data-section : DATA'

  append_ast_node(p, DataSectionDirectiveNode)

def p_text_section(p):
  'text-section : TEXT'

  append_ast_node(p, TextSectionDirectiveNode)

def p_set_directive(p):
  '''set-directive : SET ID COMMA number
                   | SET ID COMMA ID
                   | SET ID COMMA DOT
                   '''
  append_ast_node(p, SetDirectiveNode, p[2], p[4])

# Data slots
def p_slot_definition(p):
  '''slot-definition : ascii-definition
                     | byte-definition
                     | word-definition
                     | short-definition
                     | space-definition
                     | string-definition
                     '''
  pass

def __do_slot_definition(p, klass):
  if len(p) == 3:
    append_ast_node(p, klass, p[2])

  elif len(p) == 4:
    append_ast_node(p, klass, p[3])

  elif len(p) == 7:
    append_ast_node(p, LabelNode, p[2])
    append_ast_node(p, klass, p[6])

  elif len(p) == 8:
    append_ast_node(p, LabelNode, p[2])
    append_ast_node(p, klass, p[7])

  else:
    assert False, 'len(p) == %d' % len(p)

def p_ascii_definition(p):
  '''ascii-definition : ASCII SCONST
                      | TYPE ID COMMA ASCII COMMA SCONST
                      '''

  __do_slot_definition(p, AsciiNode)

def p_byte_definition(p):
  '''byte-definition : BYTE expression
                     | TYPE ID COMMA BYTE COMMA expression
                     '''

  __do_slot_definition(p, ByteNode)

def p_string_definition(p):
  '''string-definition : STRING SCONST
                       | TYPE ID COMMA STRING COMMA SCONST
                       '''

  __do_slot_definition(p, StringNode)

def p_space_definition(p):
  '''space-definition : SPACE number
                      | TYPE ID COMMA SPACE COMMA number
                      '''

  __do_slot_definition(p, SpaceNode)

def p_short_definition(p):
  '''short-definition : SHORT expression
                      | TYPE ID COMMA SHORT COMMA expression
                      '''

  __do_slot_definition(p, ShortNode)

def p_word_definition(p):
  '''word-definition : WORD expression
                     | TYPE ID COMMA WORD COMMA expression
                     '''

  __do_slot_definition(p, WordNode)

# Label
def p_label(p):
  'label : ID COLON'

  append_ast_node(p, LabelNode, p[1])

# Operands
def p_operand(p):
  '''operand : register-operand
             | immediate-operand
             '''
  p[0] = p[1]

def p_immediate_operand(p):
  '''immediate-operand : numeric-operand
                       | reference-operand
                       '''
  p[0] = p[1]

def p_register_operand(p):
  '''register-operand : REGISTER'''

  from ..cpu.registers import REGISTER_NAMES

  p[0] = RegisterOperand(REGISTER_NAMES.index(p[1]))

def p_numeric_operand(p):
  'numeric-operand : number'

  p[0] = ImmediateOperand(p[1])

def p_reference_operand(p):
  'reference-operand : ID'

  p[0] = ReferenceOperand(p[1])

def p_bo_operand(p):
  '''bo-operand : register-operand
                | register-operand LBRAC immediate-operand RBRAC
                '''

  if len(p) == 2:
    p[0] = BOOperand(p[1], ImmediateOperand(0))

  else:
    p[0] = BOOperand(p[1], p[3])

# Instructions
def p_instr(p):
  '''instruction : noop-instr
                 | unop-instr-r
                 | unop-instr-ri
                 | binop-instr-r-i
                 | binop-instr-r-r
                 | binop-instr-r-ri
                 | load-instr
                 | save-instr
                 | triop-instr
                 '''
  pass

def p_instr_noop(p):
  '''noop-instr : NOP
                | RETINT
                | RET
                | CLI
                | STI
                | RST
                | IDLE
                | LPM
                | FPTC
                | PUSHW
                | POPW
                | POPUW
                | SWPL
                | DUP
                | DUP2
                | DROP
                | DIVL
                | MODL
                | INCL
                | DECL
                | ADDL
                | MULL
                | UDIVL
                | UMODL
                | SYMDIVL
                | SYMMODL
                | PUSHL
                | POPL
                '''

  append_ast_node(p, InstructionNode, p[1], ())

def p_instr_unop(p):
  '''unop-instr-r-name  : DEC
                        | INC
                        | NOT
                        | POP
                        | SETE
                        | SETNE
                        | SETZ
                        | SETNZ
                        | SETO
                        | SETNO
                        | SETS
                        | SETNS
                        | SETL
                        | SETLE
                        | SETGE
                        | SETG
                        | SAVEW
                        | LOADW
                        | LOADUW
     unop-instr-ri-name : BE
                        | BNE
                        | BS
                        | BNS
                        | BZ
                        | BNZ
                        | BO
                        | BNO
                        | BL
                        | BLE
                        | BGE
                        | BG
                        | CALL
                        | HLT
                        | INT
                        | J
                        | SIS
                        | PUSH
     unop-instr-r       : unop-instr-r-name register-operand
     unop-instr-ri      : unop-instr-ri-name operand
     '''

  if len(p) == 2:
    p[0] = p[1]
    return

  append_ast_node(p, InstructionNode, p[1], (p[2],))

def p_instr_binop(p):
  '''binop-instr-r-i-name  : LI
                           | LIU
                           | LA
     binop-instr-r-r-name  : CTR
                           | CTW
                           | MOV
                           | SWP
                           | SAVE
                           | LOAD
     binop-instr-r-ri-name : ADD
                           | AND
                           | CMP
                           | CMPU
                           | DIV
                           | IPI
                           | MOD
                           | MUL
                           | OR
                           | SELE
                           | SELNE
                           | SELZ
                           | SELNZ
                           | SELS
                           | SELNS
                           | SELO
                           | SELNO
                           | SELL
                           | SELLE
                           | SELGE
                           | SELG
                           | SHL
                           | SHR
                           | SHRS
                           | SUB
                           | UDIV
                           | XOR
     binop-instr-r-i       : binop-instr-r-i-name register-operand COMMA immediate-operand
     binop-instr-r-r       : binop-instr-r-r-name register-operand COMMA register-operand
     binop-instr-r-ri      : binop-instr-r-ri-name register-operand COMMA operand
     '''

  if len(p) == 2:
    p[0] = p[1]
    return

  append_ast_node(p, InstructionNode, p[1], (p[2], p[4]))

def p_instr_load(p):
  '''load-instr-name : LB
                     | LS
                     | LW
     load-instr      : load-instr-name register-operand COMMA bo-operand
     '''

  if len(p) == 2:
    p[0] = p[1]
    return

  append_ast_node(p, InstructionNode, p[1], (p[2], p[4]))

def p_instr_save(p):
  '''save-instr-name : STB
                     | STS
                     | STW
     save-instr      : save-instr-name bo-operand COMMA register-operand
     '''

  if len(p) == 2:
    p[0] = p[1]
    return

  append_ast_node(p, InstructionNode, p[1], (p[2], p[4]))

def p_instr_triop(p):
  'triop-instr : CAS register-operand COMMA register-operand COMMA register-operand'

  append_ast_node(p, InstructionNode, p[1], (p[2], p[4], p[6]))

def p_error(t):
  if not t:
    # EOF
    return

  loc = t.lexer.location.copy()
  loc.lineno = t.lineno - loc.lineno
  loc.column = t.lexer.parser.lexpos_to_lineno(t.lexpos)

  from ..errors import AssemblyParseError
  raise AssemblyParseError(token = t, location = loc, line = t.lexer.parser.lineno_to_line(t.lineno))

class AssemblyParser(object):
  def __init__(self, lexer, logger = None):
    self._lexer = lexer
    self._logger = logger

    self.location = SourceLocation(filename = None, lineno = 0)

    self._parser = ply.yacc.yacc()

  def lexpos_to_lineno(self, lexpos):
    last_cr = self.input_text.rfind('\n', 0, lexpos)
    if last_cr < 0:
      last_cr = 0

    return lexpos - last_cr - 1

  def lineno_to_line(self, lineno):
    # there must be elegant way...
    for i, line in enumerate(self.input_text.split('\n')):
      if i + 1 == lineno:
        return line

    return None

  def parse(self, s, root):
    self.input_text = s

    self._parser.location = self.location
    self._parser.root = root

    self._lexer.location = self.location
    self._lexer.root = root

    self._lexer._lexer.location = self.location
    self._lexer._lexer.root = root

    self._lexer.parser = self
    self._lexer._lexer.parser = self

    return self._parser.parse(s, lexer = self._lexer, tracking = True)
