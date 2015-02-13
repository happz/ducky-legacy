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


;$DEFCODE "(", 1, $F_IMMED, PAREN
;  li $W, 0 ; depth counter
;.__PAREN_loop:
;  call &.__KEY
;  cmp r0, 0x40
;  be &.__PAREN_enter
;  cmp r0, 0x41
;  be &.__PAREN_exit
;  j &.__PAREN_loop
;.__PAREN_enter:
;  inc $W
;  j &.__PAREN_loop
;.__PAREN_exit:
;  dec $W
;  bnz &.__PAREN_loop
;  $NEXT


$DEFCODE "CORE", 4, 0, CORE
  j &.__CMP_false


$DEFCODE "CORE-EXT", 8, 0, COREEXT
  j &.__CMP_false


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


$DEFCODE "ALIGNED", 7, 0, ALIGNED
  ; ( addr -- addr )
  pop $W
  $align2 $W
  push $W
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
  cmp $W, 0
  ble &.__SPACES_next
  call &writec
  dec $W
  j &.__SPACES_loop
.__SPACES_next:
  $NEXT


$DEFCODE "FORGET", 6, 0, FORGET
  call &.__WORD
  call &.__FIND
  li $W, &var_LATEST
  li $X, &var_HERE
  lw $Y, r0
  stw $W, $Y
  stw $X, r0
  $NEXT


$DEFCODE "?HIDDEN", 7, 0, ISHIDDEN
  pop $W
  add $W, $wr_flags
  lb $W, $W
  and $W, $F_HIDDEN
  bz &.__CMP_false
  j &.__CMP_true


$DEFCODE "?IMMEDIATE", 10, 0, ISIMMEDIATE
  pop $W
  add $W, $wr_flags
  lb $W, $W
  and $W, $F_IMMED
  bz &.__CMP_false
  j &.__CMP_true


; - Conditions --------------------------------------------------------------------------


$DEFWORD "IF", 2, $F_IMMED, IF
  .int &TICK
  .int &ZBRANCH
  .int &COMMA
  .int &HERE
  .int &FETCH
  .int &LIT
  .int 0
  .int &COMMA
  .int &EXIT


$DEFWORD "ELSE", 4, $F_IMMED, ELSE
  .int &TICK
  .int &BRANCH
  .int &COMMA
  .int &HERE
  .int &FETCH
  .int &LIT
  .int 0
  .int &COMMA
  .int &SWAP
  .int &DUP
  .int &HERE
  .int &FETCH
  .int &SWAP
  .int &SUB
  .int &SWAP
  .int &STORE
  .int &EXIT


$DEFWORD "THEN", 4, $F_IMMED, THEN
  .int &DUP
  .int &HERE
  .int &FETCH
  .int &SWAP
  .int &SUB
  .int &SWAP
  .int &STORE
  .int &EXIT


; - Loops -------------------------------------------------------------------------------


$DEFCODE "RECURSE", 7, $F_IMMED, RECURSE
  li r0, &var_LATEST
  lw r0, r0
  call &.__TCFA
  call &.__COMMA
  $NEXT


$DEFCODE "BEGIN", 5, $F_IMMED, BEGIN
  ; ( -- HERE )
  li r0, &var_HERE
  lw r0, r0
  push r0
  $NEXT


$DEFCODE "WHILE", 5, $F_IMMED, WHILE
  ; ( -- HERE )
  li r0, &ZBRANCH
  call &.__COMMA
  li r0, &var_HERE
  lw r0, r0
  push r0
  li r0, 0
  call &.__COMMA
  $NEXT


$DEFWORD "UNTIL", 5, $F_IMMED, UNTIL
  .int &TICK
  .int &ZBRANCH
  .int &COMMA
  .int &HERE
  .int &FETCH
  .int &SUB
  .int &COMMA
  .int &EXIT


; - Stack -------------------------------------------------------------------------------

$DEFCODE "DEPTH", 5, 0, DEPTH
  ; ( -- n )
  li $W, &var_SZ
  lw $W, $W
  push sp
  pop $X
  sub $W, $X
  div $W, $CELL_SIZE
  push $W
  $NEXT


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


$DEFCODE "2OVER", 5, 0, TWOOVER
  ; ( a b c d -- a b c d a b )
  lw $W, sp[4]
  lw $X, sp[6]
  push $X
  push $W
  $NEXT


; - Strings -----------------------------------------------------------------------------

$DEFCODE "UWIDTH", 6, 0, UWIDTH
  ; ( u -- width )
  ; Returns the width (in characters) of an unsigned number in the current base
  pop r0
  call &.__UWIDTH
  push r0
  $NEXT

.__UWIDTH:
  li $W, &var_BASE
  lw $W, $W
  mov $X, r0
  li r0, 1
.__UWIDTH_loop:
  div $X, $W
  bz &.__UWIDTH_quit
  inc r0
  j &.__UWIDTH_loop
.__UWIDTH_quit:
  ret


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
  mul $W, $CELL_SIZE
  push $W
  $NEXT


$DEFCODE "ALLOT", 5, 0, ALLOT
  ; (n -- )
  pop $W ; amount
  li $X, &var_HERE
  lw $Y, $X
  add $Y, $W
  stw $X, $Y
  $NEXT


$DEFCODE "ALIGN", 5, 0, ALIGN
  ; ( -- )
  li $W, &var_HERE
  lw $X, $W
  $align2 $X
  stw $W, $X
  $NEXT


; - Arithmetics -------------------------------------------------------------------------

$DEFCODE "LSHIFT", 6, 0, LSHIFT
  ; ( n u -- n )
  pop $W
  pop $X
  shiftl $X, $W
  push $X
  $NEXT


$DEFCODE "RSHIFT", 6, 0, RSHIFT
  ; ( n u -- n )
  pop $W
  pop $X
  shiftr $X, $W
  push $X
  $NEXT


$DEFCODE "2*", 2, 0, TWOSTAR
  ; ( n -- n )
  pop $W
  shiftl $W, 1
  push $W
  $NEXT


$DEFCODE "2/", 2, 0, TWOSLASH
  ; ( n -- n )
  pop $W
  mov $X, $W
  shiftr $W, 1
  and $X, 0x8000
  bz &.__TWOSLASH_next
  or $W, 0x8000
.__TWOSLASH_next:
  push $W
  $NEXT


$DEFCODE "U<", 2, 0, ULT
  ; ( a b -- flag )
  pop $W
  pop $X
  cmpu $X, $W
  bl &.__CMP_true
  j &.__CMP_false


$DEFCODE "U>", 2, 0, UGT
  ; ( a b -- flag )
  pop $W
  pop $X
  cmpu $X, $W
  bg &.__CMP_true
  j &.__CMP_false


$DEFCODE "MAX", 3, 0, MAX
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  bg &.__MIN_greater
  push $X
  j &.__MIN_next
.__MIN_greater:
  push $W
.__MIN_next:
  $NEXT


$DEFCODE "MIN", 3, 0, MIN
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  bl &.__MIN_lower
  push $X
  j &.__MIN_next
.__MIN_lower:
  push $W
.__MIN_next:
  $NEXT


$DEFCODE "ABS", 3, 0, ABS
  ; ( n -- n )
  pop $W
  cmp $W, 0
  bge &.__ABS_next
  mul $W, -1
.__ABS_next:
  push $W
  $NEXT

convert_S2D:
  ; r0 - single-cell input
  ; r0, r1 - double-cell output
  li r1, 0
  cmp r0, 0
  bge &.__convert_S2D_quit
  not r1
.__convert_S2D_quit:
  ret


$DEFCODE "S>D", 3, 0, STOD
  ; ( n -- d )
  pop r0
  call &convert_S2D
  push r0
  push r1
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
  pop r0 ; n2
  call &convert_S2D
  mov $W, r0
  mov $X, r1
  pop r0 ; n1
  call &convert_S2D
  mull $W, $X, r0, r1
  push $W
  push $X
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- d )
  j &code_MSTAR


; This is fake - exceptions are not implemented yet
$DEFCODE "ABORT", 5, 0, ABORT
  call &code_BYE

