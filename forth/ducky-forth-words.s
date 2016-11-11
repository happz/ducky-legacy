/*
// A minimal FORTH kernel for Ducky virtual machine
//
// This was written as an example and for educating myself, no higher ambitions intended.
//
// Heavily based on absolutely amazing FORTH tutorial by
// Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
//
//
// This file contains implementation of FORTH words
// that are not part of basic FORTH kernel, i.e. words
// that can be implemented using kernel words.
//
// I decided to hardcode some of core FORTH words
// this way to save time during bootstraping and testing
// of Ducky FORTH implementation. Some words are also
// implemented in assembler - those I find too simple to
// use DEFWORD for them...
//
*/

#include "forth.h"
#include <arch/math.h>


DEFCSTUB("(", 1, F_IMMED, PAREN)
  // ( "ccc<paren>" -- )


DEFCSTUB(".(", 2, F_IMMED, DOT_PAREN)
  // ( "ccc<paren>" -- )


DEFCSTUB("CR", 2, 0x00, CR)
  // ( -- )


DEFCSTUB("SPACE", 5, 0x00, SPACE)
  // ( -- )


DEFCSTUB_10("SPACES", 6, 0x00, SPACES)
  // ( n -- )


  .data

__environment_query_result:
  .word 0x00000000
  .word 0x00000000

DEFCODE("ENVIRONMENT?", 12, 0x00, ENVIRONMENT_QUERY)
  // ( c-addr u -- false | i*x true )
  pop r0
  mov r1, TOS

  la r2, __environment_query_result
  call do_ENVIRONMENT_QUERY

  cmp r0, 0x00 // UNKNOWN
  be __ENVIRONMENT_QUERY_unknown

  cmp r0, 0x01 // NUMBER
  be __ENVIRONMENT_QUERY_number

  cmp r0, 0x02 // DOUBLE_NUMBER
  be __ENVIRONMENT_QUERY_double_number

  cmp r0, 0x03 // TRUE
  be __ENVIRONMENT_QUERY_true

  cmp r0, 0x04 // FALSE
  be __ENVIRONMENT_QUERY_false

  hlt 0x79

__ENVIRONMENT_QUERY_number:
  la W, __environment_query_result
  lw W, W
  push W
  j __ENVIRONMENT_QUERY_known

__ENVIRONMENT_QUERY_double_number:
  la W, __environment_query_result
  lw X, W
  push X
  lw X, W[CELL]
  push X
  j __ENVIRONMENT_QUERY_known

__ENVIRONMENT_QUERY_true:
  PUSH_TRUE(W)
  j __ENVIRONMENT_QUERY_known

__ENVIRONMENT_QUERY_false:
  push FORTH_FALSE
  j __ENVIRONMENT_QUERY_known

__ENVIRONMENT_QUERY_known:
  LOAD_TRUE(TOS)
  NEXT

__ENVIRONMENT_QUERY_unknown:
  li TOS, FORTH_FALSE
  NEXT


DEFWORD("[COMPILE]", 9, F_IMMED, BCOMPILE)
  .word DWORD
  .word FIND
  .word DROP
  .word COMMA
  .word EXIT


DEFCSTUB("POSTPONE", 8, F_IMMED, POSTPONE)


// - Character constants -----------------------------------------------------------------

#define DEFCHAR(_name, _len, _label, _c) \
DEFCODE(_name, _len, 0x00, _label) \
  push TOS                         \
  li TOS, _c                       \
  NEXT

DEFCHAR("'\\\\n'", 4, CHAR_NL,          10)
DEFCHAR("'\\\\r'", 4, CHAR_CR,          13)
DEFCHAR("BL",      2, CHAR_SPACE,       32)
DEFCHAR("':'",     3, CHAR_COLON,       58)
DEFCHAR("'//'",    3, CHAR_SEMICOLON,   59)
DEFCHAR("'('",     3, CHAR_LPAREN,      40)
DEFCHAR("')'",     3, CHAR_RPAREN,      41)
DEFCHAR("'\"'",    3, CHAR_DOUBLEQUOTE, 34)
DEFCHAR("'0'",     3, CHAR_ZERO,        48)
DEFCHAR("'-'",     3, CHAR_MINUS,       45)
DEFCHAR("'.'",     3, CHAR_DOT,         46)


// - Helpers -----------------------------------------------------------------------------

DEFCODE("NOT", 3, 0x00, NOT)
  // ( flag -- flag )
  li W, 0xFFFF
  liu W, 0xFFFF
  xor TOS, W
  NEXT


DEFCODE("NEGATE", 6, 0x00, NEGATE)
  // ( n .. -n )
  li X, 0x00
  sub X, TOS
  mov TOS, X
  NEXT


DEFCSTUB_10("LITERAL", 7, F_IMMED, LITERAL)
  // ( x -- )


DEFWORD("WITHIN", 6, 0x00, WITHIN)
  // ( test low high -- flag )
  .word OVER
  .word SUB
  .word TOR
  .word SUB
  .word FROMR
  .word ULT
  .word EXIT


DEFCODE("ALIGNED", 7, 0x00, ALIGNED)
  // ( addr -- addr )
  ALIGN_CELL(TOS)
  NEXT


DEFCODE("DECIMAL", 7, 0x00, DECIMAL)
  la W, var_BASE
  li X, 10
  stw W, X
  NEXT


DEFCODE("HEX", 3, 0x00, HEX)
  la W, var_BASE
  li X, 16
  stw W, X
  NEXT



DEFCODE("FORGET", 6, 0x00, FORGET)
  hlt 0x25
  call __read_dword
  //call __FIND
  la W, var_LATEST
  la X, var_DP
  lw Y, r0
  stw W, Y
  stw X, r0
  NEXT


DEFCODE("?HIDDEN", 7, 0x00, ISHIDDEN)
  mov W, TOS
  pop TOS
  add W, WR_FLAGS
  lb W, W
  and W, F_HIDDEN
  TF_FINISH(ISHIDDEN, bnz)


DEFCODE("?IMMEDIATE", 10, 0x00, ISIMMEDIATE)
  mov W, TOS
  pop TOS
  add W, WR_FLAGS
  lb W, W
  and W, F_IMMED
  TF_FINISH(ISIMMEDIATE, bnz)


DEFCODE("ROLL", 4, 0x00, ROLL)
  // ( xu xu-1 ... x0 u -- xu-1 ... x0 xu )

  // u is in TOS
  mul TOS, CELL
  mov W, sp
  add W, TOS
  lw W, W // xu
  mov r0, sp
  add r0, CELL
  mov r1, sp
  mov r2, TOS
  call memmove
  add sp, CELL
  mov TOS, W

  NEXT


DEFCODE("2>R", 3, 0x00, TWOTOR)
  // ( x1 x2 -- ) ( R:  -- x1 x2 )
  pop W
  PUSHRSP(W)
  PUSHRSP(TOS)
  pop TOS
  NEXT


DEFCODE("2R@", 3, 0x00, TWORFETCH)
  // ( -- x1 x2 ) ( R:  x1 x2 -- x1 x2 )
  push TOS
  lw TOS, RSP[CELL]
  push TOS
  lw TOS, RSP
  NEXT


DEFCODE("2R>", 3, 0x00, TWORFROM)
  // ( -- x1 x2 ) ( R:  x1 x2 -- )
  push TOS
  POPRSP(TOS)
  POPRSP(W)
  push W
  NEXT


// - Control structures --------------------------------------------------------------------------

DEFCSTUB_01("IF", 2, F_IMMED, IF)
  // ( C: -- orig )
  // ( R: x -- )

DEFCSTUB_11("ELSE", 4, F_IMMED, ELSE)
  // ( C: orig1 -- orig2 )
  // ( R: -- )

DEFCSTUB_10("THEN", 4, F_IMMED, THEN)
  // (C: orig -- )
  // (R: -- )

DEFCSTUB_01("BEGIN", 5, F_IMMED, BEGIN)
  // ( C: -- dest )
  // ( R: -- )

DEFCODE("WHILE", 5, F_IMMED, WHILE)
  // ( C: dest -- orig dest )
  // ( R: x -- )
  call do_WHILE
  push r0
  NEXT

DEFCSTUB_10("UNTIL", 5, F_IMMED, UNTIL)
  // ( C: dest -- )
  // ( R: x -- )

DEFCSTUB_20("REPEAT", 6, F_IMMED, REPEAT)
  // ( C: orig dest -- )
  // ( R: -- )

DEFCSTUB_10("AGAIN", 5, F_IMMED, AGAIN)
  // ( C: dest -- )
  // ( R: -- )

DEFWORD("CASE", 4, F_IMMED, CASE)
  .word LIT
  .word 0x00
  .word EXIT


DEFWORD("OF", 2, F_IMMED, OF)
  .word BRACKET_TICK
  .word OVER
  .word COMMA
  .word BRACKET_TICK
  .word EQU
  .word COMMA
  .word IF
  .word BRACKET_TICK
  .word DROP
  .word COMMA
  .word EXIT


DEFWORD("ENDOF", 5, F_IMMED, ENDOF)
  .word ELSE
  .word EXIT


DEFWORD("ENDCASE", 7, F_IMMED, ENDCASE)
  .word BRACKET_TICK
  .word DROP
  .word COMMA
  .word QDUP
  .word ZBRANCH
  .word 0x00000010
  .word THEN
  .word BRANCH
  .word 0xFFFFFFEC
  .word EXIT

DEFCODE("RECURSE", 7, F_IMMED, RECURSE)
  la r0, var_LATEST
  lw r0, r0
  call fw_code_field
  call COMPILE
  NEXT


// - Stack -------------------------------------------------------------------------------

DEFCODE("DEPTH", 5, 0x00, DEPTH)
  // ( -- n )
  push TOS
  la TOS, var_SZ
  lw TOS, TOS
  sub TOS, sp
  div TOS, CELL
  dec TOS                             // account for that TOS push at the beginning of DEPTH
  NEXT


DEFWORD("NIP", 3, 0x00, NIP)
  // ( a b -- b )
  .word SWAP
  .word DROP
  .word EXIT


DEFWORD("TUCK", 4, 0x00, TUCK)
  // ( a b -- a b a )
  .word SWAP
  .word OVER
  .word EXIT


DEFCODE("2OVER", 5, 0x00, TWOOVER)
  // ( a b c d -- a b c d a b )
  push TOS
  lw TOS, sp[12]
  push TOS
  lw TOS, sp[12]
  NEXT


DEFCODE("PICK", 4, 0x00, PICK)
  // ( x_n ... x_1 x_0 n -- x_u ... x_1 x_0 x_n )
  mov X, sp
  mul TOS, CELL
  add TOS, X
  lw TOS, TOS
  NEXT


// - Strings -----------------------------------------------------------------------------

DEFCODE("S\"", 2, F_IMMED, SQUOTE)
  // ( -- c-addr u )
  la r0, SQUOTE_LITSTRING
  call do_LITSTRING
  NEXT


DEFCODE("C\"", 2, F_IMMED, CQUOTE)
  // ( -- c-addr )
  la r0, CQUOTE_LITSTRING
  call do_LITSTRING
  NEXT

DEFCODE(".\"", 2, F_IMMED, DOTQUOTE)
  la r0, SQUOTE_LITSTRING
  call do_LITSTRING

  // compile TELL
  la W, TELL
  la X, var_DP
  lw Y, X
  stw Y, W
  add Y, CELL
  stw X, Y

  NEXT


DEFCODE("UWIDTH", 6, 0x00, UWIDTH)
  // ( u -- width )
  // Returns the width (in characters) of an unsigned number in the current base
  mov r0, TOS
  call do_UWIDTH
  mov TOS, r0
  NEXT


DEFCODE("C,", 2, 0x00, CSTORE)
  // ( char -- )
  la X, var_DP
  lw Y, X
  stb Y, TOS
  inc Y
  stw X, Y
  pop TOS
  NEXT


DEFCODE("CHARS", 5, 0x00, CHARS)
  // ( n1 -- n2 )
  // this is in fact NOP - each char is 1 byte, n1 chars need n1 bytes of memory
  NEXT


DEFCODE("COUNT", 5, 0x00, COUNT)
  // ( c-addr -- c-addr u )
  lb W, TOS
  inc TOS
  push TOS
  mov TOS, W
  NEXT




// - Memory ------------------------------------------------------------------------------

DEFVAR("HEAP-START", 10, 0x00, HEAP_START, 0xFFFFFFFF)
DEFVAR("HEAP", 4, 0x00, HEAP, 0xFFFFFFFF)


DEFCODE(">BODY", 5, 0x00, TOBODY)
  // ( xt -- a-addr )
  add TOS, CELL
  add TOS, CELL
  NEXT


DEFCODE("CELLS", 5, 0x00, CELLS)
  // ( n -- cell_size*n )
  mul TOS, CELL
  NEXT


DEFCODE("CELL+", 5, 0x00, CELLADD)
  // ( a-addr1 -- a-addr2 )
  add TOS, CELL
  NEXT


DEFCODE("CHAR+", 5, 0x00, CHARADD)
  // ( a-addr1 -- a-addr2 )
  inc TOS
  NEXT


DEFCODE("2@", 2, 0x00, TWOFETCH)
  // ( a-addr -- x1 x2 )
  lw X, TOS
  lw Y, TOS[CELL]
  push Y
  mov TOS, X
  NEXT


DEFCODE("2!", 2, 0x00, TWOSTORE)
  // ( x1 x2 a-addr -- )
  pop W // x2
  pop X // x1
  stw TOS, W
  stw TOS[4], X
  pop TOS
  NEXT


DEFCODE("ALLOT", 5, 0x00, ALLOT)
  // (n -- )
  la X, var_DP
  lw Y, X
  add Y, TOS
  stw X, Y
  pop TOS
  NEXT


DEFCODE("ALIGN", 5, 0x00, ALIGN)
  // ( -- )
  la W, var_DP
  lw X, W
  ALIGN_CELL(X)
  stw W, X
  NEXT


DEFCODE("UNUSED", 6, 0x00, UNUSED)
  // ( -- u )
  la W, var_UP
  lw W, W
  la X, var_DP
  lw X, X
  sub X, W
  li W, USERSPACE_SIZE
  sub W, X
  push TOS
  mov TOS, W
  NEXT


DEFCODE("FILL", 4, 0x00, FILL)
  // ( c-addr u char -- )
  mov r1, TOS
  pop r2
  pop r0
  call memset
  pop TOS
  NEXT


DEFCODE("ERASE", 5, 0x00, ERASE)
  // ( addr u -- )
  pop r0
  mov r1, TOS
  pop TOS
  call bzero
  NEXT


DEFCODE("BUFFER:", 7, 0x00, BUFFER_COLON)
  // ( u "<spaces>name" -- )
  // name Execution: ( -- a-addr )

  call __read_dword
  call do_HEADER_COMMA

  mov r0, TOS
  pop TOS
  call malloc

  la W, var_DP                       // now, compile simple word to push address on stack
  lw Z, W

  la Y, DOCOL
  stw Z, Y
  add Z, CELL

  la Y, LIT
  stw Z, Y
  add Z, CELL

  stw Z, r0
  add Z, CELL

  la Y, EXIT
  stw Z, Y
  add Z, CELL

  stw W, Z

  NEXT


DEFCODE("MOVE", 4, 0x00, MOVE)
  // ( addr1 addr2 u -- )
  mov r2, TOS
  pop r0
  pop r1
  pop TOS
  call memmove
  NEXT


DEFCODE("ALLOCATE", 8, 0x00, ALLOCATE)
  // ( u -- a-addr ior )
  li W, 0xFFFF
  liu W, 0xFFFF
  cmp TOS, W
  be __ALLOCATE_fail
  mov r0, TOS
  call malloc
  push r0
  li TOS, 0x00
  NEXT
__ALLOCATE_fail:
  push 0x00
  li TOS, 0x01
  NEXT


DEFCODE("FREE", 4, 0x00, FREE)
  // ( a-addr - ior )
  mov r0, TOS
  call free
  li TOS, 0x00
  NEXT


DEFCODE("RESIZE", 6, 0x00, RESIZE)
  // ( a-addr1 u -- a-addr2 ior )
  li W, 0xFFFF
  liu W, 0xFFFF
  cmp TOS, W
  be __RESIZE_fail
  pop r0
  mov r1, TOS
  call realloc
  push r0
  li TOS, 0x00
  NEXT
__RESIZE_fail:
  li TOS, 0x01
  NEXT


DEFCODE("MARKER", 6, 0x00, MARKER)
  la W, var_LATEST                   //
  lw W, W                            // keep LATEST for later use
  la X, var_DP                       // and keep DP and its value, too
  lw Y, X

  call __read_dword
  call do_HEADER_COMMA

  lw Z, X                            // load new DP - it has been modified by HEADER,

  la r0, DOCOL
  stw Z, r0
  add Z, CELL

  la r0, LIT
  stw Z, r0
  add Z, CELL

  stw Z, W
  add Z, CELL

  la r0, LATEST
  stw Z, r0
  add Z, CELL

  la r0, STORE
  stw Z, r0
  add Z, CELL

  la r0, LIT
  stw Z, r0
  add Z, CELL

  stw Z, Y
  add Z, CELL

  la r0, DP
  stw Z, r0
  add Z, CELL

  la r0, STORE
  stw Z, r0
  add Z, CELL

  la r0, EXIT
  stw Z, r0
  add Z, CELL

  stw X, Z

  NEXT


// - Arithmetics -------------------------------------------------------------------------

DEFCODE("LSHIFT", 6, 0x00, LSHIFT)
  // ( n u -- n )
  pop W
  shiftl W, TOS
  mov TOS, W
  NEXT


DEFCODE("RSHIFT", 6, 0x00, RSHIFT)
  // ( n u -- n )
  pop W
  shiftr W, TOS
  mov TOS, W
  NEXT


DEFCODE("2*", 2, 0x00, TWOSTAR)
  // ( n -- n )
  shiftl TOS, 1
  NEXT


DEFCODE("2/", 2, 0x00, TWOSLASH)
  // ( n -- n )
  li Y, 0x0000
  liu Y, 0x8000
  mov W, TOS
  shiftr TOS, 1
  and W, Y
  bz __TWOSLASH_next
  or TOS, Y
__TWOSLASH_next:
  NEXT


DEFCODE("U<", 2, 0x00, ULT)
  // ( a b -- flag )
  pop W
  cmpu W, TOS
  TF_FINISH(ULT, bl)


DEFCODE("U>", 2, 0x00, UGT)
  // ( a b -- flag )
  pop W
  cmpu W, TOS
  TF_FINISH(UGT, bg)


DEFCODE("MAX", 3, 0x00, MAX)
  // ( a b -- n )
  pop W
  cmp W, TOS
  ble __MAX_next
  mov TOS, W
__MAX_next:
  NEXT


DEFCODE("MIN", 3, 0x00, MIN)
  // ( a b -- n )
  pop W
  cmp W, TOS
  bge __MIN_next
  mov TOS, W
__MIN_next:
  NEXT


DEFCODE("ABS", 3, 0x00, ABS)
  // ( n -- n )
  cmp TOS, 0x00
  bge __ABS_next
  mul TOS, -1
__ABS_next:
  NEXT


// - Printing ----------------------------------------------------------------------------

DEFCODE("#>", 2, 0x00, NUMBERSIGNGREATER)
  // ( xd -- c-addr u )
  la X, pno_ptr    // pno_ptr addr
  lw Y, X          // pno_ptr

  la W, pno_buffer
  add W, CONFIG_PNO_BUFFER_SIZE
  sub W, Y
  stw sp, Y
  mov TOS, W
  NEXT

DEFCODE("SIGN", 4, 0x00, SIGN)
  pop r0
  swp r0, TOS
  cmp r0, 0x00
  bns __SIGN_next
  li r0, 0x2D
  call pno_add_char
__SIGN_next:
  NEXT


DEFCODE("HOLD", 4, 0x00, HOLD)
  mov r0, TOS
  pop TOS
  call pno_add_char
  NEXT


DEFCSTUB_20("HOLDS", 5, 0x00, HOLDS)
  // ( c-addr u -- )


DEFCODE("#", 1, 0x00, NUMBERSIGN)
  // ( ud1 - ud2 )
  la W, var_BASE
  lw W, W
  push TOS          // push TOS on stack so we can use pop to load it to math stack
  sis MATH_INST_SET
  popl                // ud1
  loadw W           // ud1 n
  dup2               // ud1 n ud1 n
  umodl              // ud1 n rem
  savew r0           // ud1 n
  udivl              // quot
  save TOS, X      // split quot between TOS and stack
  sis DUCKY_INST_SET
  push X
  call pno_add_number
  NEXT


DEFCODE("#S", 2, 0x00, NUMBERSIGNS)
  // ( ud1 - 0 0 )
  la W, var_BASE
  lw W, W
  push TOS          // push TOS on stack so we can use pop to load it to math stack
  sis MATH_INST_SET
  popl                // ud1
__NUMBERSIGNS_loop:
  sis MATH_INST_SET // turn math inst set on at the beginning of each iteration
  loadw W           // ud base
  dup2               // ud base ud base
  umodl              // ud base rem
  savew r0           // ud base
  udivl              // quot
  dup                // quot quot
  save Y, Z        // quot
  sis DUCKY_INST_SET
  call pno_add_number

  cmp Y, Z
  bnz __NUMBERSIGNS_loop
  sis MATH_INST_SET
  drop               //
  sis DUCKY_INST_SET

  push 0x00
  li TOS, 0x00
  NEXT


DEFCODE(">NUMBER", 7, 0x00, TONUMBER)
  // ( ud1 c-addr1 u1 -- ud2 c-addr2 u2 )
                                  // u1 is in TOS
  pop W                          // c-addr
  sis MATH_INST_SET
  popl                             //  -- ud1
  sis DUCKY_INST_SET
  la r10, pno_chars              // cache char table ptr
  la r11, var_BASE               // cache BASE
  lw r11, r11
  mov r12, r10                    // compute pointer to the digit right *after* the BASE reach
  add r12, r11
  cmp TOS, 0x00                     // check if there are any chars left
__TONUMBER_loop:
  bz __TONUMBER_complete
  lb X, W                       // fetch char
  mov r13, r10                    // lookup char in table
__TONUMBER_find_char:
  lb r14, r13
  cmp r14, X
  be __TONUMBER_char_found       // found
  inc r13
  cmp r13, r12                    // if our table ptr points to the char outside the base, not found
  be __TONUMBER_complete
  j __TONUMBER_find_char
__TONUMBER_char_found:
  sub r13, r10                    // char represents value (offset - PNO chars table)
  sis MATH_INST_SET              // add digit to accumulator
  loadw r11                       // ud1 -- ud1 base
  mull                            // ud1 base -- (ud1 * base)
  loadw r13                       // (ud1 * base) -- (ud1 * base) digit
  addl                            // (ud1 * base) digit -- (ud1 * base + digit) = ud1
  sis DUCKY_INST_SET
  inc W                          // move to the next digit
  dec TOS                        // and decrement remaining chars counter
  j __TONUMBER_loop
__TONUMBER_complete:
  sis MATH_INST_SET
  pushl                            // save accumulator
  sis DUCKY_INST_SET
  push W                         // save string pointer
  NEXT


DEFCODE("U.R", 3, 0x00, UDOTR)
  // ( u n -- )
  pop X // load U from stack
  mov r0, X
  call do_UWIDTH
  sub TOS, r0 // how many spaces we need to print? may be negative, but SPACES dont care
  swp TOS, r0
  call do_SPACES
  mov r0, X
  call print_u32
  pop TOS
  NEXT


DEFCODE(".R", 2, 0x00, DOTR)
  // ( n n -- )
  li X, 0x00                             // is N negative?
  pop r0                               // get N
  mov Y, r0                           // save N for later
  bns __DOTR_unsigned
  li X, 1                             // yes, N is negative
  li r0, 0x00
  sub r0, Y                           // make it positive. positive is good.
__DOTR_unsigned:
  call do_UWIDTH                       // find Ns width
  sub TOS, r0                         // how many spaces we need to print? may be negative, but SPACES dont care
  sub TOS, X                         // add one character for '-' sign
  swp TOS, r0
  call do_SPACES
  mov r0, Y
  call print_i32
  pop TOS
  NEXT


DEFCODE(".S", 2, 0x00, DOTS)
  la W, var_SZ
  lw W, W
  mov X, W
  sub W, sp

  sub X, CELL                          // point to the first cell...
  sub X, CELL                          // and skip it because it's the initial TOS value
  div W, CELL
  dec W
__DOTS_loop:
  bz __DOTS_TOS
  lw r0, X
  call print_u32
  call do_SPACE
  sub X, CELL
  dec W
  j __DOTS_loop

__DOTS_TOS:
  // print TOS
  mov r0, TOS
  call print_u32
  call do_SPACE

  NEXT


DEFCODE("ID.", 3, 0x00, IDDOT)
  // ( a-addr -- )
  mov r0, TOS
  pop TOS
  call __IDDOT
  NEXT

__IDDOT:
  // void __IDDOT(void *ptr)
  // it's just about constructing arguments for write()
  push r1
  add r0, WR_NAMELEN
  lb r1, r0
  inc r0
  call puts
  call putnl
  pop r1
  ret


DEFCODE("WORDS", 5, 0x00, WORDS)
  // ( -- )
  call __WORDS
  NEXT

__WORDS:
  push r0
  push r10
  la r10, var_LATEST
  lw r10, r10
  mov r0, r10
__WORDS_loop:
  bz __WORDS_quit
  call __IDDOT
  lw r10, r10
  mov r0, r10
  j __WORDS_loop
__WORDS_quit:
  pop r10
  pop r0
  ret
