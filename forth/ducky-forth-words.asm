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

$DEFWORD "[COMPILE]", 9, $F_IMMED, BCOMPILE
  .int &WORD
  .int &FIND
  .int &TCFA
  .int &COMMA
  .int &EXIT


  .section .rodata
  .type word_not_found_msg, string
  .string "Word not found: "

word_not_found:
  li r0, &word_not_found_msg
  call &writes
  call &write_word_buffer
  call &halt


$DEFCODE "POSTPONE", 8, $F_IMMED, POSTPONE
  call &.__WORD
  $unpack_word_for_find
  call &.__FIND
  cmp r0, r0
  bz &word_not_found
  call &.__TCFA
  call &.__COMMA
  $NEXT


$DEFCODE "(", 1, $F_IMMED, PAREN
  li $W, 1 ; depth counter
.__PAREN_loop:
  call &.__KEY
  cmp r0, 0x28
  be &.__PAREN_enter
  cmp r0, 0x29
  be &.__PAREN_exit
  j &.__PAREN_loop
.__PAREN_enter:
  inc $W
  j &.__PAREN_loop
.__PAREN_exit:
  dec $W
  bnz &.__PAREN_loop
  $NEXT


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
  $unpack_word_for_find
  call &.__FIND
  li $W, &var_LATEST
  li $X, &var_DP
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
  .int &LIT
  .int &ZBRANCH
  .int &COMMA
  .int &HERE
  .int &LIT
  .int 0
  .int &COMMA
  .int &EXIT


$DEFWORD "ELSE", 4, $F_IMMED, ELSE
  .int &LIT
  .int &BRANCH
  .int &COMMA
  .int &HERE
  .int &LIT
  .int 0
  .int &COMMA
  .int &SWAP
  .int &DUP
  .int &HERE
  .int &SWAP
  .int &SUB
  .int &SWAP
  .int &STORE
  .int &EXIT


$DEFWORD "THEN", 4, $F_IMMED, THEN
  .int &DUP
  .int &HERE
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
  li $W, &var_DP
  lw $W, $W
  push $W
  $NEXT


$DEFCODE "WHILE", 5, $F_IMMED, WHILE
  ; ( -- HERE )
  li r0, &ZBRANCH
  call &.__COMMA
  li $W, &var_DP
  lw $W, $W
  push $W
  li r0, 0
  call &.__COMMA
  $NEXT


$DEFWORD "UNTIL", 5, $F_IMMED, UNTIL
  .int &LIT
  .int &ZBRANCH
  .int &COMMA
  .int &HERE
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


$DEFCODE "PICK", 4, 0, PICK
  ; ( x_n ... x_1 x_0 n -- x_u ... x_1 x_0 x_n )
  pop $W
  push sp
  pop $X
  mul $W, $CELL
  add $X, $W
  lw $W, $W
  push $W
  $NEXT


; - Strings -----------------------------------------------------------------------------


__SQUOTE_read_and_store:
  ; > r0 - ptr
  ; < r0 - length
  push r1 ; ptr
  push r2 ; length
  mov r1, r0 ; save ptr - r0 is used by __KEY
  li r2, 0
.__SQUOTE_read_and_store_loop:
  call &.__KEY
  cmp r0, 0x22
  be &.__SQUOTE_read_and_store_finish
  stb r1, r0
  inc r1
  inc r2
  j &.__SQUOTE_read_and_store_loop
.__SQUOTE_read_and_store_finish:
  mov r0, r2
  pop r2
  pop r1
  ret


$DEFCODE "S\"", 2, $F_IMMED, SQUOTE
  li r0, &var_STATE
  lw r0, r0

  li r4, &var_DP ; &DP
  lw r5, r4        ; HERE

  cmp r0, 0
  be &.__SQUOTE_exec

  ; r6 - &length
  ; r7 - length
  li r6, &LITSTRING
  stw r5, r6
  add r5, $CELL
  mov r6, r5       ; &strlen
  add r5, $CELL
  mov r0, r5
  call &__SQUOTE_read_and_store
  stw r6, r0
  add r5, r0
  $align2 r5
  stw r4, r5
  j &.__SQUOTE_next

.__SQUOTE_exec:
  mov r0, r5
  call &__SQUOTE_read_and_store
  push r5
  push r0

.__SQUOTE_next:
  $NEXT


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
  ; ( char -- )
  pop $W
  li $X, &var_DP
  lw $Y, $X
  stb $Y, $W
  inc $Y
  stw $X, $Y
  $NEXT


$DEFCODE "CHARS", 5, 0, CHARS
  ; ( n1 -- n2 )
  ; this is in fact NOP - each char is 1 byte, n1 chars need n1 bytes of memory
  $NEXT


; - Memory ------------------------------------------------------------------------------

$DEFCODE "CELLS", 5, 0, CELLS
  ; ( n -- cell_size*n )
  pop $W
  mul $W, $CELL_SIZE
  push $W
  $NEXT


$DEFCODE "CELL+", 5, 0, CELLADD
  ; ( a-addr1 -- a-addr2 )
  pop $W
  add $W, $CELL
  push $W
  $NEXT


$DEFCODE "CHAR+", 5, 0, CHARADD
  ; ( a-addr1 -- a-addr2 )
  pop $W
  inc $W
  push $W
  $NEXT


$DEFCODE "2@", 2, 0, TWOFETCH
  ; ( a-addr -- x1 x2 )
  pop $W
  lw $X, $W
  lw $Y, $W[$CELL]
  push $Y
  push $X
  $NEXT


$DEFCODE "2!", 2, 0, TWOSTORE
  ; ( x1 x2 a-addr -- )
  pop $W
  pop $X
  pop $Y
  stw $W, $X
  stw $W[$CELL], $Y
  $NEXT


$DEFCODE "ALLOT", 5, 0, ALLOT
  ; (n -- )
  pop $W ; amount
  li $X, &var_DP
  lw $Y, $X
  add $Y, $W
  stw $X, $Y
  $NEXT


$DEFCODE "ALIGN", 5, 0, ALIGN
  ; ( -- )
  li $W, &var_DP
  lw $X, $W
  $align2 $X
  stw $W, $X
  $NEXT


$DEFCODE "UNUSED", 6, 0, UNUSED
  ; ( -- u )
  li $W, &var_UP
  lw $W, $W
  li $X, &var_DP
  lw $X, $X
  sub $X, $W
  li $W, $USERSPACE_SIZE
  sub $W, $X
  div $W, $CELL
  push $W
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


;
; Double-cell integer operations
;
; This routines use math coprocessor's (MC) interrupt
;
.macro DC_dup:
  li r0, $MATH_DUPL
  int $INT_MATH
.end

.macro DC_mul:
  li r0, $MATH_MULL
  int $INT_MATH
.end

.macro DC_div:
  li r0, $MATH_DIVL
  int $INT_MATH
.end

.macro DC_mod:
  li r0, $MATH_MODL
  int $INT_MATH
.end

.macro DC_symdiv:
  li r0, $MATH_SYMDIVL
  int $INT_MATH
.end

.macro DC_symmod:
  li r0, $MATH_SYMMODL
  int $INT_MATH
.end

.macro DC_itos_to_l:
  li r0, $MATH_ITOL
  pop r1
  int $INT_MATH
.end

.macro DC_utos_to_l:
  li r0, $MATH_UTOL
  pop r1
  int $INT_MATH
.end

.macro DC_ir_to_l reg:
  li r0, $MATH_ITOL
  mov r1, #reg
  int $INT_MATH
.end

.macro DC_dtos_to_l:
  li r0, $MATH_IITOL
  pop r2
  pop r1
  int $INT_MATH
.end

.macro DC_l_to_itos:
  li r0, $MATH_LTOI
  int $INT_MATH
  push r1
.end

.macro DC_l_to_dtos:
  li r0, $MATH_LTOII
  int $INT_MATH
  push r1
  push r2
.end

$DEFCODE "S>D", 3, 0, STOD
  ; ( n -- d )
  $DC_itos_to_l
  $DC_l_to_dtos
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
  $DC_itos_to_l
  $DC_itos_to_l
  $DC_mul
  $DC_l_to_dtos
  $NEXT

$DEFCODE "FM/MOD", 6, 0, FMMOD
  ; ( d1 n1 -- n2 n3 )
  pop $W

  $DC_dtos_to_l
  $DC_dup

  $DC_ir_to_l $W
  $DC_mod
  $DC_l_to_itos

  $DC_ir_to_l $W
  $DC_div
  $DC_l_to_itos

  $NEXT


$DEFCODE "SM/REM", 6, 0, SMMOD
  ; ( d1 n1 -- n2 n3 )
  pop $W

  $DC_dtos_to_l
  $DC_dup

  $DC_ir_to_l $W
  $DC_symmod
  $DC_l_to_itos

  $DC_ir_to_l $W
  $DC_symdiv
  $DC_l_to_itos

  $NEXT


$DEFCODE "UM/MOD", 6, 0, UMMOD
  j &code_FMMOD


$DEFCODE "*/", 2, 0, STARSLASH
  ; ( n1 n2 n3 -- n4 )
  pop $W
  pop $X
  pop $Y
  $DC_ir_to_l $Y
  $DC_ir_to_l $X
  $DC_mul
  $DC_ir_to_l $W
  $DC_div
  $DC_l_to_itos
  $NEXT


$DEFCODE "*/MOD", 5, 0, STARMOD
  ; ( n1 n2 n3 -- n4 n5 )
  pop $W
  pop $X
  pop $Y

  $DC_ir_to_l $Y
  $DC_ir_to_l $X
  $DC_mul
  $DC_dup
  $DC_ir_to_l $W
  $DC_mod
  $DC_l_to_itos
  $DC_ir_to_l $W
  $DC_div
  $DC_l_to_itos
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- ud )
  $DC_utos_to_l
  $DC_utos_to_l
  $DC_mul
  $DC_l_to_dtos
  $NEXT


; This is fake - exceptions are not implemented yet
$DEFCODE "ABORT", 5, 0, ABORT
  call &code_BYE

