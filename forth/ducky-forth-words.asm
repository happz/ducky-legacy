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

.include "ducky-forth-defs.asm"

;
; - Environment queries -----------------------------------------------------------------
;

.macro ENV_ENTRY name, str, len:
  .section .rodata

  .type ENV_ENTRY_NAME_#name, ascii
  .ascii #str

  .type ENV_ENTRY_LEN_#name, int
  .int #len

  .text

.__ENV_ENTRY_HANDLER_#name:
.end

.macro ENV_ENTRY_CHECK name:
  ; save string info
  push r0
  push r1
  ; load entry string info
  li r2, &ENV_ENTRY_NAME_#name
  li r3, &ENV_ENTRY_LEN_#name
  lw r3, r3
  ; compare strings
  call &strcmp
  ; restore string info
  pop r1
  pop r2 ; r0 => r2 - pop it from stack, we'll need it later
  ; did strings match?
  cmp r0, 0
  bnz &.__ENVIRONMENT_QUERY_next_#name
  push $FORTH_TRUE
  j &.__ENV_ENTRY_HANDLER_#name
.__ENVIRONMENT_QUERY_next_#name:
  mov r0, r2 ; restore string ptr
.end

$ENV_ENTRY COUNTED_STRING, "/COUNTED-STRING", 15
  push $STRING_SIZE
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY CORE, "CORE", 4
  push $FORTH_FALSE
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY CORE_EXT, "CORE-EXT", 8
  push $FORTH_FALSE
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY FLOORED, "FLOORED", 7
  push $FORTH_TRUE
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY MAX_CHAR, "MAX-CHAR", 8
  push 127
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY RETURN_STACK_CELLS, "RETURN-STACK-CELLS", 18
  li r0, $RSTACK_SIZE
  div r0, $CELL
  push r0
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY STACK_CELLS, "STACK-CELLS", 11
  li r0, $PAGE_SIZE
  div r0, $CELL
  push r0
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY ADDRESS_UNIT_BITS, "ADDRESS-UNIT-BITS", 17
  push 8
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY MAX_D, "MAX-D", 5
  push 0xFFFF
  push 0x7FFF
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY MAX_UD, "MAX-UD", 6
  push 0xFFFF
  push 0xFFFF
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY MAX_N, "MAX-N", 5
  push 0x7FFF
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY MAX_U, "MAX-U", 5
  push 0xFFFF
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY ENV_MEMORY_ALLOC, "MEMORY-ALLOC", 12
  push $FORTH_TRUE
  j &.__ENVIRONMENT_QUERY_next

$ENV_ENTRY ENV_MEMORY_ALLOC_EXT, "MEMORY-ALLOC-EXT", 16
  push $FORTH_TRUE
  j &.__ENVIRONMENT_QUERY_next

$DEFCODE "ENVIRONMENT?", 12, 0, ENVIRONMENT_QUERY
  ; ( c-addr u -- false | i*x true )
  pop r1 ; u
  pop r0 ; c-addr

  $ENV_ENTRY_CHECK RETURN_STACK_CELLS
  $ENV_ENTRY_CHECK COUNTED_STRING
  $ENV_ENTRY_CHECK CORE
  $ENV_ENTRY_CHECK CORE_EXT
  $ENV_ENTRY_CHECK ADDRESS_UNIT_BITS
  $ENV_ENTRY_CHECK MAX_D
  $ENV_ENTRY_CHECK MAX_UD
  $ENV_ENTRY_CHECK MAX_N
  $ENV_ENTRY_CHECK MAX_U
  $ENV_ENTRY_CHECK STACK_CELLS
  $ENV_ENTRY_CHECK FLOORED
  $ENV_ENTRY_CHECK MAX_CHAR
  $ENV_ENTRY_CHECK ENV_MEMORY_ALLOC
  $ENV_ENTRY_CHECK ENV_MEMORY_ALLOC_EXT

  push $FORTH_FALSE
  j &.__ENVIRONMENT_QUERY_next

.__ENVIRONMENT_QUERY_next:
  $NEXT


$DEFWORD "[COMPILE]", 9, $F_IMMED, BCOMPILE
  .int &WORD
  .int &FIND
  .int &DROP
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


; - Character constants -----------------------------------------------------------------

$DEFCODE "'\\\\n'", 4, 0, CHAR_NL
  ; ( -- <newline char> )
  push 10
  $NEXT

$DEFCODE "'\\\\r'", 4, 0, CHAR_CR
  ; ( -- <carriage return char>
  push 13
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
  .int &CHAR_CR
  .int &EMIT
  .int &CHAR_NL
  .int &EMIT
  .int &EXIT


$DEFCODE "SPACE", 5, 0, SPACE
  ; ( -- )
  call &.__SPACE
  $NEXT

.__SPACE:
  li r0, 32
  j &.__EMIT


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

  cmp $X, $W
  bl &.__WITHIN_L_LOWER_R
  bg &.__WITHIN_R_LOWER_L
  j &.__CMP_false

.__WITHIN_L_LOWER_R:
  cmp $Y, $X
  bl &.__CMP_false
  cmp $Y, $W
  bge &.__CMP_false
  j &.__CMP_true

.__WITHIN_R_LOWER_L:
  cmp $Y, $W
  bl &.__CMP_false
  cmp $Y, $X
  bge &.__CMP_false
  j &.__CMP_true

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


$DEFCODE "ROLL", 4, 0, ROLL
  ; ( xu xu-1 ... x0 u -- xu-1 ... x0 xu )
  pop $W ; u
  mul $W, $CELL

  mov r0, sp
  add r0, $W
  lw $X, r0 ; xu

  mov r0, sp
  mov r1, sp
  add r1, $CELL
  mov r2, $W

  call &memmove

  stw sp, $X

  $NEXT


$DEFCODE "2>R", 3, 0, TWOTOR
  ; ( x1 x2 -- ) ( R:  -- x1 x2 )
  pop $W
  pop $X
  $pushrsp $X
  $pushrsp $W
  $NEXT


$DEFCODE "2R@", 3, 0, TWORFETCH
  ; ( -- x1 x2 ) ( R:  x1 x2 -- x1 x2 )
  lw $W, $RSP
  lw $X, $RSP[2]
  push $X
  push $W
  $NEXT


$DEFCODE "2R>", 3, 0, TWORFROM
  ; ( -- x1 x2 ) ( R:  x1 x2 -- )
  $poprsp $W
  $poprsp $X
  push $X
  push $W
  $NEXT

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
  div $W, $CELL
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


__string_read_and_store:
  ; > r0 - ptr
  ; < r0 - length
  push r1 ; ptr
  push r2 ; length
  mov r1, r0 ; save ptr - r0 is used by __KEY
  li r2, 0
.__string_read_and_store_loop:
  call &.__KEY
  cmp r0, 0x22
  be &.__string_read_and_store_finish
  stb r1, r0
  inc r1
  inc r2
  j &.__string_read_and_store_loop
.__string_read_and_store_finish:
  mov r0, r2
  pop r2
  pop r1
  ret


.__string_quote:
  ; r0 contains LITSTRING variant this routine should push
  push r1
  push r4
  push r5

  li r1, &var_STATE
  lw r1, r1

  li r4, &var_DP
  lw r5, r4

  cmp r1, 0
  be &.__string_quote_exec

  ; r6 - &length
  ; r7 - length
  stw r5, r0
  add r5, $CELL
  mov r6, r5       ; &strlen
  inc r5
  mov r0, r5
  call &__string_read_and_store
  stb r6, r0
  add r5, r0
  $align2 r5
  stw r4, r5

.__string_quote_quit:
  pop r5
  pop r4
  pop r1
  ret

.__string_quote_exec:
  mov r4, r0
  mov r0, r5
  call &__string_read_and_store
  ; r0 = string length
  ; r5 = HERE before storing string, i.e. its length cell, c-addr
  ; r4 = original LITSTRING variant
  cmp r4, &SQUOTE_LITSTRING
  bne &.__string_quote_cquote_litstring
  ; r5 points to HERE before storing string, i.e. its length cell, c-addr
  inc r5 ; now it points to string itself
  push r5 ; push it
  push r0 ; and push string length
  j &.__string_quote_quit
.__string_quote_cquote_litstring:
  push r5 ; push c-addr
  j &.__string_quote_quit


$DEFCODE "S\"", 2, $F_IMMED, SQUOTE
  ; ( -- c-addr u )
  li r0, &SQUOTE_LITSTRING
  call &.__string_quote
  $NEXT


$DEFCODE "C\"", 2, $F_IMMED, CQUOTE
  ; ( -- c-addr )
  li r0, &CQUOTE_LITSTRING
  call &.__string_quote
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


$DEFCODE "COUNT", 5, 0, COUNT
  ; ( c-addr -- c-addr u )
  pop $W
  lb $X, $W
  inc $W
  push $W
  push $X
  $NEXT


$DEFCODE ".(", 2, $F_IMMED, DOT_PAREN
.__DOT_PAREN_loop:
  call &.__KEY
  cmp r0, 41 ; cmp with ')'
  be &.__DOT_PAREN_quit
  call &.__EMIT
  j &.__DOT_PAREN_loop
.__DOT_PAREN_quit:
  $NEXT


; - Memory ------------------------------------------------------------------------------


$DEFCODE ">BODY", 5, 0, TOBODY
  ; ( xt -- a-addr )
  pop $W
  add $W, $CELL
  add $W, $CELL
  push $W
  $NEXT


$DEFCODE "CELLS", 5, 0, CELLS
  ; ( n -- cell_size*n )
  pop $W
  mul $W, $CELL
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


$DEFCODE "FILL", 4, 0, FILL
  ; ( c-addr u char -- )
  pop $W ; char
  pop $X ; u
  pop $Y ; c-addr

  cmp $W, 0
  ble &.__FILL_next

.__FILL_loop:
  cmp $X, 0
  bz &.__FILL_next
  stb $Y, $W
  inc $Y
  dec $X
  j &.__FILL_loop

.__FILL_next:
  $NEXT


memcpy:
  ; r0 - src
  ; r1 - dst
  ; r2 - length
  cmp r2, 0
  bz &.__memcpy_quit
  push r3
.__memcpy_loop:
  lb r3, r0
  stb r1, r3
  inc r0
  inc r1
  dec r2
  bnz &.__memcpy_loop
  pop r3
.__memcpy_quit:
  ret

memmove:
  ; r0 - src
  ; r1 - dst
  ; r2 - length
  ; r3 - tmp ptr

  push r3
  li r3, &var_DP
  lw r3, r3

  push r0
  push r1
  push r2
  mov r1, r3
  call &memcpy
  pop r2
  pop r1
  pop r0

  push r0
  push r1
  push r2
  mov r0, r3
  call &memcpy
  pop r2
  pop r1
  pop r0
  pop r3
  ret


$DEFCODE "MOVE", 4, 0, MOVE
  ; ( addr1 addr2 u -- )
  pop r2 ; u
  pop r1 ; addr2
  pop r0 ; addr1

  call &memmove
  $NEXT


mm_alloc:
  push r1
  ; convert number of bytes to number of pages, add 2 bytes for pages count
  add r0, $CELL
  $align_page r0
  div r0, $PAGE_SIZE
  mov r1, r0 ; save pages count
  call &mm_area_alloc
  stw r0, r1 ; save pages count at the beggining of the area
  add r0, $CELL ; and return the rest of the area to the caller
  pop r1
  ret


mm_free:
  push r1
  sub r0, $CELL
  lw r1, r0
  call &mm_area_free
  pop r1
  ret


$DEFCODE "ALLOCATE", 8, 0, ALLOCATE
  ; ( u -- a-addr ior )
  pop $W

  li r0, $MM_OP_UNUSED
  int $INT_MM
  mul r0, $PAGE_SIZE
  cmpu $W, r0
  bg &.__ALLOCATE_oom

  mov r0, $W
  call &mm_alloc
  push r0
  push 0
  $NEXT

.__ALLOCATE_oom:
  push 0xFFFF ; address
  push 0xFFFF ; 'failed' IOR
  $NEXT


$DEFCODE "FREE", 4, 0, FREE
  ; ( a-addr - ior )
  pop r0 ; address
  call &mm_free
  push 0
  $NEXT


$DEFCODE "RESIZE", 6, 0, RESIZE
  ; ( a-addr1 u -- a-addr2 ior )
  pop $W ; u
  pop $X ; a-addr

  li r0, $MM_OP_UNUSED
  int $INT_MM
  mul r0, $PAGE_SIZE
  cmpu $W, r0
  bg &.__RESIZE_oom

  ; allocate new area
  mov r0, $W
  call &mm_alloc
  mov r5, r0 ; save new memory area

  ; get size of the new area
  sub r0, $CELL
  lw r4, r0 ; save new memory area size

  ; find size of the original area
  mov r0, $X
  sub r0, $CELL
  lw r3, r0 ; save old memory area size

  cmp r4, r3
  ble &.__RESIZE_new_smaller

  mov r2, r3
  j &.__RESIZE_copy

.__RESIZE_new_smaller:
  mov r2, r4

.__RESIZE_copy:
  mul r2, $PAGE_SIZE
  sub r2, $CELL

  mov r0, $X
  mov r1, r5
  call &memcpy

  mov r0, $X
  call &mm_free

  push r5
  push 0
  j &.__RESIZE_next

.__RESIZE_oom:
  push $X
  push 0xFFFF

.__RESIZE_next:
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
$DEFCODE "S>D", 3, 0, STOD
  ; ( n -- d )
  sis $INST_SET_MATH
  pop r1
  itol
  ltoii
  push r1
  push r2
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
  sis $INST_SET_MATH
  pop r1
  itol
  pop r1
  itol
  mull
  ltoii
  push r1
  push r2
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "FM/MOD", 6, 0, FMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $INST_SET_MATH
  pop $W
  pop r2
  pop r1
  iitol
  dupl
  mov r1, $W
  itol
  modl
  ltoi
  push r1
  mov r1, $W
  itol
  divl
  ltoi
  push r1
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "SM/REM", 6, 0, SMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $INST_SET_MATH
  pop $W
  pop r2
  pop r1
  iitol
  dupl
  mov r1, $W
  itol
  symmodl
  ltoi
  push r1
  mov r1, $W
  itol
  symdivl
  ltoi
  push r1
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "UM/MOD", 6, 0, UMMOD
  j &code_FMMOD


$DEFCODE "*/", 2, 0, STARSLASH
  ; ( n1 n2 n3 -- n4 )
  sis $INST_SET_MATH
  pop $W
  pop $X
  pop $Y
  mov r1, $Y
  itol
  mov r1, $X
  itol
  mull
  mov r1, $W
  itol
  divl
  ltoi
  push r1
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "*/MOD", 5, 0, STARMOD
  ; ( n1 n2 n3 -- n4 n5 )
  sis $INST_SET_MATH
  pop $W
  pop $X
  pop $Y
  mov r1, $Y
  itol
  mov r1, $X
  itol
  mull
  dupl
  mov r1, $W
  itol
  modl
  ltoi
  push r1
  mov r1, $W
  itol
  divl
  ltoi
  push r1
  sis $INST_SET_DUCKY
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- ud )
  sis $INST_SET_MATH
  pop r1
  utol
  pop r1
  utol
  mull
  ltoii
  push r1
  push r2
  sis $INST_SET_DUCKY
  $NEXT


; - Printing ----------------------------------------------------------------------------

$DEFCODE "U.", 2, 0, UDOT
  pop r0
  call &.__UDOT
  $NEXT

.__UDOT:
  ; BASE
  push r1
  li r1, &var_BASE
  lw r1, r1

  push r0 ; save r0 for mod later
  udiv r0, r1
  bz &.__UDOT_print
  call &.__UDOT

.__UDOT_print:
  pop r0 ; restore saved number and mod it
  mod r0, r1
  cmp r0, 10
  bge &.__UDOT_print_letters
  add r0, 48

.__UDOT_emit:
  call &.__EMIT
  pop r1 ; restore saved r1 (BASE)
  ret

.__UDOT_print_letters:
  sub r0, 10
  add r0, 65
  j &.__UDOT_emit


$DEFCODE ".S", 2, 0, DOTS
  mov $W, sp
  li $X, &var_SZ
  lw $X, $X

.__DOTS_loop:
  lw r0, $W
  call &.__UDOT
  call &.__SPACE
  add $W, $CELL
  cmp $W, $X
  bl &.__DOTS_loop
  $NEXT


; This is fake - exceptions are not implemented yet
$DEFCODE "ABORT", 5, 0, ABORT
  call &code_BYE
