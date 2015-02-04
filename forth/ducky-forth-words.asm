; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;
;
; This file contains implementation of FORTH words
; that are not part of basic FORTH kernel, i.e. words
; that can be implemented using kernel words.
;
; I decided to hardcode some of core FORTH words
; this way to save time during bootstraping and testing
; of Ducky FORTH implementation. Some words are also
; implemented in assembler - those I find too simple to
; use DEFWORD for them...
;

; - Character constants -----------------------------------------------------------------

$DEFCODE "'\\\\n'", 4, 0, CHAR_NL
  ; ( -- <newline char> )
  push 10
  $NEXT

$DEFCODE "BL", 2, 0, CHAR_SPACE
  ; ( -- <space> )
  push 32
  $NEXT

$DEFWORD "':'", 3, 0, CHAR_COLON
  .int &LIT
  .int 58
  .int &EXIT

$DEFWORD "';'", 3, 0, CHAR_SEMICOLON
  .int &LIT
  .int 59
  .int &EXIT

$DEFWORD "'('", 3, 0, CHAR_LPAREN
  .int &LIT
  .int 40
  .int &EXIT

$DEFWORD "')'", 3, 0, CHAR_RPAREN
  .int &LIT
  .int 41
  .int &EXIT

$DEFWORD "'\"'", 3, 0, CHAR_DOUBLEQUOTE
  .int &LIT
  .int 34
  .int &EXIT

$DEFWORD "'A'", 3, 0, CHAR_A
  .int &LIT
  .int 65
  .int &EXIT

$DEFWORD "'0'", 3, 0, CHAR_ZERO
  .int &LIT
  .int 48
  .int &EXIT

$DEFWORD "'-'", 3, 0, CHAR_MINUS
  .int &LIT
  .int 45
  .int &EXIT

$DEFWORD "'.'", 3, 0, CHAR_DOT
  .int &LIT
  .int 46
  .int &EXIT


; - Helpers -----------------------------------------------------------------------------

$DEFWORD "CR", 2, 0, CR
  ; ( -- )
  .int &CHAR_NL
  .int &EMIT
  .int &EXIT


$DEFWORD "SPACE", 5, 0, SPACE
  ; ( -- )
  .int &CHAR_SPACE
  .int &EMIT
  .int &EXIT


$DEFWORD "NOT", 3, 0, NOT
  ; ( flag -- flag )
  .int &ZEQU
  .int &EXIT


$DEFCODE "NEGATE", 6, 0, NEGATE
  ; ( n .. -n )
  pop $W
  li $X, 0
  sub $X, $W
  push $X
  $NEXT


$DEFWORD "LITERAL", 7, $F_IMMED, LITERAL
  .int &LIT
  .int &LIT
  .int &COMMA
  .int &COMMA
  .int &EXIT


$DEFCODE "WITHIN", 6, 0, WITHIN
  ; ( c a b -- flag )
  pop $W ; b
  pop $X ; a
  pop $Y ; c
  cmp $X, $Y
  bl &.__CMP_false
  cmp $Y, $W
  bge &.__CMP_false
  j &.__CMP_true


$DEFCODE "DEPTH", 5, 0, DEPTH
  ; ( -- n )
  li $W, &var_SZ
  lw $W, $W
  push sp
  pop $X
  sub $W, $X
  push $W
  $NEXT


$DEFCODE "ALIGNED", 7, 0, ALIGNED
  ; ( addr -- addr )
  pop $W
  $align2 $W
  push $W
  $NEXT


$DEFCODE "ALIGN", 5, 0, ALIGN
  ; ( -- )
  li $W, &var_HERE
  lw $X, $W
  $align2 $X
  stw $W, $X
  $NEXT


$DEFCODE "DECIMAL", 7, 0, DECIMAL
  li $W, &var_BASE
  li $X, 10
  stw $W, $X
  $NEXT


$DEFCODE "HEX", 3, 0, HEX
  li $W, &var_BASE
  li $X, 16
  stw $W, $X
  $NEXT


$DEFCODE "SPACES", 6, 0, SPACES
  pop $W
  li r0, 32
.__SPACES_loop:
  cmp $W, $W
  bz &.__SPACES_next
  call &writec
  dec $W
  j &.__SPACES_loop
.__SPACES_next:
  $NEXT


; - Conditions --------------------------------------------------------------------------


; - Loops -------------------------------------------------------------------------------


; - Stack -------------------------------------------------------------------------------

$DEFWORD "NIP", 3, 0, NIP
  ; ( a b -- b )
  .int &SWAP
  .int &DROP
  .int &EXIT


$DEFWORD "TUCK", 4, 0, TUCK
  ; ( a b -- a b a )
  .int &SWAP
  .int &OVER
  .int &EXIT


; - Strings -----------------------------------------------------------------------------

$DEFCODE "C,", 2, 0, CSTORE
  li $W, &var_HERE
  lw $X, $W
  pop $Y
  stb $X, $Y
  inc $X
  stw $W, $X
  $NEXT


; - Memory ------------------------------------------------------------------------------

$DEFCODE "CELLS", 5, 0, CELLS
  ; ( n -- cell_size*n )
  pop $W
  mul $W, 2
  push $W
  $NEXT


$DEFCODE "ALLOT", 5, 0, ALLOT
  ; (n -- )
  pop $W ; amount
  li $X, &var_HERE
  lw $Y, $X
  mov $Z, $Y
  add $Y, $W
  stw $X, $Y
  push $Z
  $NEXT


$DEFWORD "ARRAY", 5, 0, ARRAY
  .int &CELLS
  .int &ALLOT
  .int &CREATE
  .int &LIT
  .int &DOCOL
  .int &COMMA
  .int &LIT
  .int &LIT
  .int &COMMA
  .int &COMMA
  .int &LIT
  .int &EXIT
  .int &COMMA
  .int &EXIT


; This is fake - exceptions are not implemented yet
$DEFWORD "ABORT", 5, 0, ABORT
  .int &BYE
  .int &EXIT

