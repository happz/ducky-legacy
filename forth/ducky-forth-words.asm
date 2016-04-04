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
.include "math.asm"

;
; - Environment queries -----------------------------------------------------------------
;

.macro ENV_ENTRY name, str, len:
  .section .rodata

  .align 4

  .type ENV_ENTRY_NAME_#name, ascii
  .ascii #str

  .align 4

  .type ENV_ENTRY_LEN_#name, int
  .int #len

  .text

__ENV_ENTRY_HANDLER_#name:
.end

.macro ENV_ENTRY_CHECK name:
  ; restore input string
  mov r0, $X
  mov r1, $W
  ; load entry string info
  la r2, &ENV_ENTRY_NAME_#name
  la r3, &ENV_ENTRY_LEN_#name
  lw r3, r3
  ; compare strings
  call &strcmp
  ; did strings match?
  cmp r0, 0
  bnz &__ENVIRONMENT_QUERY_next_#name
  ; found!
  j &__ENV_ENTRY_HANDLER_#name
__ENVIRONMENT_QUERY_next_#name:
  mov r0, r2 ; restore string ptr
.end

$ENV_ENTRY COUNTED_STRING, "/COUNTED-STRING", 15
  push $STRING_SIZE
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY CORE, "CORE", 4
  push $FORTH_FALSE
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY CORE_EXT, "CORE-EXT", 8
  push $FORTH_FALSE
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY FLOORED, "FLOORED", 7
  $push_true $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY MAX_CHAR, "MAX-CHAR", 8
  push 127
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY RETURN_STACK_CELLS, "RETURN-STACK-CELLS", 18
  li r0, $RSTACK_SIZE
  div r0, $CELL
  push r0
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY STACK_CELLS, "STACK-CELLS", 11
  li r0, $DSTACK_SIZE
  div r0, $CELL
  push r0
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY ADDRESS_UNIT_BITS, "ADDRESS-UNIT-BITS", 17
  push 8
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY MAX_D, "MAX-D", 5
  li $W, 0xFFFF
  liu $W, 0xFFFF
  push $W
  li $W, 0xFFFF
  liu $W, 0x7FFF
  push $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY MAX_UD, "MAX-UD", 6
  li $W, 0xFFFF
  liu $W, 0xFFFF
  push $W
  push $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY MAX_N, "MAX-N", 5
  li $W, 0xFFFF
  liu $W, 0x7FFF
  push $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY MAX_U, "MAX-U", 5
  li $W, 0xFFFF
  liu $W, 0xFFFF
  push $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY ENV_MEMORY_ALLOC, "MEMORY-ALLOC", 12
  $push_true $W
  j &__ENVIRONMENT_QUERY_next_pass

$ENV_ENTRY ENV_MEMORY_ALLOC_EXT, "MEMORY-ALLOC-EXT", 16
  $push_true $W
  j &__ENVIRONMENT_QUERY_next_pass

$DEFCODE "ENVIRONMENT?", 12, 0, ENVIRONMENT_QUERY
  ; ( c-addr u -- false | i*x true )
.ifdef FORTH_TIR
  pop $X
  mov $W, $TOS
.else
  pop $W ; u
  pop $X ; c-addr
.endif

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

.ifdef FORTH_TIR
  li $TOS, $FORTH_FALSE
.else
  push $FORTH_FALSE
.endif
  j &__ENVIRONMENT_QUERY_next

__ENVIRONMENT_QUERY_next_pass:
.ifdef FORTH_TIR
  $load_true $TOS
.else
  $push_true $W
.endif

__ENVIRONMENT_QUERY_next:
  $NEXT


$DEFWORD "[COMPILE]", 9, $F_IMMED, BCOMPILE
  .int &DWORD
  .int &FIND
  .int &DROP
  .int &COMMA
  .int &EXIT


  .section .rodata
  .align 4
  .type word_not_found_msg, string
  .string "Word not found: "

word_not_found:
  la r0, &word_not_found_msg
  call &writes
  call &write_word_buffer
  call &halt


$DEFCODE "POSTPONE", 8, $F_IMMED, POSTPONE
  call &__read_dword_with_refill
  $unpack_word_for_find
  call &__FIND
  cmp r0, r0
  bz &word_not_found
  call &__TCFA
  call &__COMMA
  $NEXT


$DEFCODE "(", 1, $F_IMMED, PAREN
  li $W, 1 ; depth counter

__PAREN_loop:
  call &__read_dword_with_refill ; r0 - counted string
  lb $X, r0
  cmp $X, 0x0001
  bne &__PAREN_loop
  inc r0
  lb $X, r0
  cmp $X, 0x28
  be &__PAREN_enter
  cmp $X, 0x29
  be &__PAREN_exit
  j &__PAREN_loop
__PAREN_enter:
  inc $W
  j &__PAREN_loop
__PAREN_exit:
  dec $W
  bnz &__PAREN_loop
  $NEXT


; - Character constants -----------------------------------------------------------------

$DEFCODE "'\\\\n'", 4, 0, CHAR_NL
  ; ( -- <newline char> )
.ifdef FORTH_TIR
  push $TOS
  li $TOS, 10
.else
  push 10
.endif
  $NEXT


$DEFCODE "'\\\\r'", 4, 0, CHAR_CR
  ; ( -- <carriage return char>
.ifdef FORTH_TIR
  push $TOS
  li $TOS, 13
.else
  push 13
.endif
  $NEXT


$DEFCODE "BL", 2, 0, CHAR_SPACE
  ; ( -- <space> )
.ifdef FORTH_TIR
  push $TOS
  li $TOS, 32
.else
  push 32
.endif
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
  call &__SPACE
  $NEXT

__SPACE:
  li r0, 32
  j &__write_stdout


$DEFCODE "NOT", 3, 0, NOT
  ; ( flag -- flag )
  li $W, 0xFFFF
  liu $W, 0xFFFF
.ifdef FORTH_TIR
  xor $TOS, $W
.else
  pop $X
  xor $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "NEGATE", 6, 0, NEGATE
  ; ( n .. -n )
  li $X, 0
.ifdef FORTH_TIR
  sub $X, $TOS
  mov $TOS, $X
.else
  pop $W
  sub $X, $W
  push $X
.endif
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
  bl &__WITHIN_L_LOWER_R
  bg &__WITHIN_R_LOWER_L
  j &__CMP_false

__WITHIN_L_LOWER_R:
  cmp $Y, $X
  bl &__CMP_false
  cmp $Y, $W
  bge &__CMP_false
  j &__CMP_true

__WITHIN_R_LOWER_L:
  cmp $Y, $W
  bl &__CMP_false
  cmp $Y, $X
  bge &__CMP_false
  j &__CMP_true

  j &__CMP_true


$DEFCODE "ALIGNED", 7, 0, ALIGNED
  ; ( addr -- addr )
.ifdef FORTH_TIR
  $align4 $TOS
.else
  pop $W
  $align4 $W
  push $W
.endif
  $NEXT


$DEFCODE "DECIMAL", 7, 0, DECIMAL
  la $W, &var_BASE
  li $X, 10
  stw $W, $X
  $NEXT


$DEFCODE "HEX", 3, 0, HEX
  la $W, &var_BASE
  li $X, 16
  stw $W, $X
  $NEXT


$DEFCODE "SPACES", 6, 0, SPACES
.ifdef FORTH_TIR
  li r0, 32
  cmp $TOS, 0
__SPACES_loop:
  ble &__SPACES_next
  call &writec
  dec $TOS
  j &__SPACES_loop
__SPACES_next:
  pop $TOS
.else
  pop $W
  li r0, 32
__SPACES_loop:
  cmp $W, 0
  ble &__SPACES_next
  call &writec
  dec $W
  j &__SPACES_loop
__SPACES_next:
.endif
  $NEXT


$DEFCODE "FORGET", 6, 0, FORGET
  call &__read_dword_with_refill
  $unpack_word_for_find
  call &__FIND
  la $W, &var_LATEST
  la $X, &var_DP
  lw $Y, r0
  stw $W, $Y
  stw $X, r0
  $NEXT


$DEFCODE "?HIDDEN", 7, 0, ISHIDDEN
.ifdef FORTH_TIR
  mov $W, $TOS
  pop $TOS
.else
  pop $W
.endif
  add $W, $wr_flags
  lb $W, $W
  and $W, $F_HIDDEN
  bz &__CMP_false
  j &__CMP_true


$DEFCODE "?IMMEDIATE", 10, 0, ISIMMEDIATE
.ifdef FORTH_TIR
  mov $W, $TOS
  pop $TOS
.else
  pop $W
.endif
  add $W, $wr_flags
  lb $W, $W
  and $W, $F_IMMED
  bz &__CMP_false
  j &__CMP_true


$DEFCODE "ROLL", 4, 0, ROLL
  ; ( xu xu-1 ... x0 u -- xu-1 ... x0 xu )
  hlt 0x3333
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
.ifdef FORTH_TIR
  pop $W
  $pushrsp $W
  $pushrsp $TOS
  pop $TOS
.else
  pop $W
  pop $X
  $pushrsp $X
  $pushrsp $W
.endif
  $NEXT


$DEFCODE "2R@", 3, 0, TWORFETCH
  ; ( -- x1 x2 ) ( R:  x1 x2 -- x1 x2 )
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $RSP[$CELL]
  push $TOS
  lw $TOS, $RSP
.else
  lw $W, $RSP
  lw $X, $RSP[$CELL]
  push $X
  push $W
.endif
  $NEXT


$DEFCODE "2R>", 3, 0, TWORFROM
  ; ( -- x1 x2 ) ( R:  x1 x2 -- )
.ifdef FORTH_TIR
  push $TOS
  $poprsp $TOS
  push $TOS
  $poprsp $TOS
.else
  $poprsp $W
  $poprsp $X
  push $X
  push $W
.endif
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
  la r0, &var_LATEST
  lw r0, r0
  call &__TCFA
  call &__COMMA
  $NEXT


$DEFCODE "BEGIN", 5, $F_IMMED, BEGIN
  ; ( -- HERE )
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &var_DP
  lw $TOS, $TOS
.else
  la $W, &var_DP
  lw $W, $W
  push $W
.endif
  $NEXT


$DEFCODE "WHILE", 5, $F_IMMED, WHILE
  ; ( -- HERE )
  la r0, &ZBRANCH
  call &__COMMA
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &var_DP
  lw $TOS, $TOS
.else
  la $W, &var_DP
  lw $W, $W
  push $W
.endif
  li r0, 0
  call &__COMMA
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
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &var_SZ
  lw $TOS, $TOS
  sub $TOS, sp
  div $TOS, $CELL
  dec $TOS                             ; account for that TOS push at the beginning of DEPTH
.else
  la $W, &var_SZ
  lw $W, $W
  sub $W, sp
  div $W, $CELL
  push $W
.endif
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
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, sp[12]
  push $TOS
  lw $TOS, sp[12]
.else
  lw $W, sp[8]
  lw $X, sp[12]
  push $X
  push $W
.endif
  $NEXT


$DEFCODE "PICK", 4, 0, PICK
  ; ( x_n ... x_1 x_0 n -- x_u ... x_1 x_0 x_n )
.ifdef FORTH_TIR
  mov $X, sp
  mul $TOS, $CELL
  add $TOS, $X
  lw $TOS, $TOS
.else
  pop $W
  mov $X, sp
  mul $W, $CELL
  add $X, $W
  lw $W, $W
  push $W
.endif
  $NEXT


; - Strings -----------------------------------------------------------------------------


;
; u32_t __string_read_and_store(char *ptr)
;
; Read characters from a position in input buffer by calling __read_input, and copy them
; to a buffer PTR. When quote (") is encountered, returns number of copied characters.
;
__string_read_and_store:
  ; save working registers
  push r1
  push r2
  ; save buffer pointer because r0 is used by __read_input
  mov r1, r0
  ; copy buffer address for later use
  mov r2, r0
  ; copy loop
__string_read_and_store_loop:
  call &__read_input
  ; is new character "?
  cmp r0, 0x22
  be &__string_read_and_store_finish
  ; store and iterate
  stb r1, r0
  inc r1
  j &__string_read_and_store_loop
__string_read_and_store_finish:
  ; compute number of copied characters
  mov r0, r1
  sub r0, r2
  pop r2
  pop r1
  ret


__string_quote:
  ; r0 contains LITSTRING variant this routine should push
  push r1
  push r4
  push r5

  la r1, &var_STATE
  lw r1, r1

  la r4, &var_DP
  lw r5, r4

  cmp r1, 0
  be &__string_quote_exec

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
  $align4 r5
  stw r4, r5

__string_quote_quit:
  pop r5
  pop r4
  pop r1
  ret

__string_quote_exec:
  mov r4, r0
  mov r0, r5
  call &__string_read_and_store
  ; r0 = string length
  ; r5 = HERE before storing string, i.e. its length cell, c-addr
  ; r4 = original LITSTRING variant
  cmp r4, &SQUOTE_LITSTRING
  bne &__string_quote_cquote_litstring
  ; r5 points to HERE before storing string, i.e. its length cell, c-addr
  inc r5 ; now it points to string itself
  push r5 ; push it
  push r0 ; and push string length
  j &__string_quote_quit
__string_quote_cquote_litstring:
  push r5 ; push c-addr
  j &__string_quote_quit


$DEFCODE "S\"", 2, $F_IMMED, SQUOTE
  ; ( -- c-addr u )
  la r0, &SQUOTE_LITSTRING
  call &__string_quote
  $NEXT


$DEFCODE "C\"", 2, $F_IMMED, CQUOTE
  ; ( -- c-addr )
  la r0, &CQUOTE_LITSTRING
  call &__string_quote
  $NEXT


$DEFCODE "UWIDTH", 6, 0, UWIDTH
  ; ( u -- width )
  ; Returns the width (in characters) of an unsigned number in the current base
.ifdef FORTH_TIR
  mov r0, $TOS
  call &__UWIDTH
  mov $TOS, r0
.else
  pop r0
  call &__UWIDTH
  push r0
.endif
  $NEXT

__UWIDTH:
  la $W, &var_BASE
  lw $W, $W
  mov $X, r0
  li r0, 1
__UWIDTH_loop:
  div $X, $W
  bz &__UWIDTH_quit
  inc r0
  j &__UWIDTH_loop
__UWIDTH_quit:
  ret


$DEFCODE "C,", 2, 0, CSTORE
  ; ( char -- )
.ifdef FORTH_TIR
  la $X, &var_DP
  lw $Y, $X
  stb $Y, $TOS
  inc $Y
  stw $X, $Y
  pop $TOS
.else
  pop $W
  la $X, &var_DP
  lw $Y, $X
  stb $Y, $W
  inc $Y
  stw $X, $Y
.endif
  $NEXT


$DEFCODE "CHARS", 5, 0, CHARS
  ; ( n1 -- n2 )
  ; this is in fact NOP - each char is 1 byte, n1 chars need n1 bytes of memory
  $NEXT


$DEFCODE "COUNT", 5, 0, COUNT
  ; ( c-addr -- c-addr u )
.ifdef FORTH_TIR
  lb $W, $TOS
  inc $TOS
  push $TOS
  mov $TOS, $W
.else
  pop $W
  lb $X, $W
  inc $W
  push $W
  push $X
.endif
  $NEXT


$DEFCODE ".(", 2, $F_IMMED, DOT_PAREN
__DOT_PAREN_loop:
  call &__read_input
  cmp r0, 41 ; cmp with ')'
  be &__DOT_PAREN_quit
  call &__write_stdout
  j &__DOT_PAREN_loop
__DOT_PAREN_quit:
  $NEXT


; - Memory ------------------------------------------------------------------------------


$DEFCODE ">BODY", 5, 0, TOBODY
  ; ( xt -- a-addr )
.ifdef FORTH_TIR
  add $TOS, 8
.else
  pop $W
  add $W, $CELL
  add $W, $CELL
  push $W
.endif
  $NEXT


$DEFCODE "CELLS", 5, 0, CELLS
  ; ( n -- cell_size*n )
.ifdef FORTH_TIR
  mul $TOS, $CELL
.else
  pop $W
  mul $W, $CELL
  push $W
.endif
  $NEXT


$DEFCODE "CELL+", 5, 0, CELLADD
  ; ( a-addr1 -- a-addr2 )
.ifdef FORTH_TIR
  add $TOS, $CELL
.else
  pop $W
  add $W, $CELL
  push $W
.endif
  $NEXT


$DEFCODE "CHAR+", 5, 0, CHARADD
  ; ( a-addr1 -- a-addr2 )
.ifdef FORTH_TIR
  inc $TOS
.else
  pop $W
  inc $W
  push $W
.endif
  $NEXT


$DEFCODE "2@", 2, 0, TWOFETCH
  ; ( a-addr -- x1 x2 )
.ifdef FORTH_TIR
  lw $X, $TOS
  lw $Y, $TOS[$CELL]
  push $Y
  mov $TOS, $X
.else
  pop $W
  lw $X, $W
  lw $Y, $W[$CELL]
  push $Y
  push $X
.endif
  $NEXT


$DEFCODE "2!", 2, 0, TWOSTORE
  ; ( x1 x2 a-addr -- )
.ifdef FORTH_TIR
  pop $W ; x2
  pop $X ; x1
  stw $TOS, $W
  stw $TOS[4], $X
  pop $TOS
.else
  pop $W
  pop $X
  pop $Y
  stw $W, $X
  stw $W[$CELL], $Y
.endif
  $NEXT


$DEFCODE "ALLOT", 5, 0, ALLOT
  ; (n -- )
.ifdef FORTH_TIR
  la $X, &var_DP
  lw $Y, $X
  add $Y, $TOS
  stw $X, $Y
  pop $TOS
.else
  pop $W ; amount
  la $X, &var_DP
  lw $Y, $X
  add $Y, $W
  stw $X, $Y
.endif
  $NEXT


$DEFCODE "ALIGN", 5, 0, ALIGN
  ; ( -- )
  la $W, &var_DP
  lw $X, $W
  $align4 $X
  stw $W, $X
  $NEXT


$DEFCODE "UNUSED", 6, 0, UNUSED
  ; ( -- u )
  la $W, &var_UP
  lw $W, $W
  la $X, &var_DP
  lw $X, $X
  sub $X, $W
  li $W, $USERSPACE_SIZE
  sub $W, $X
  div $W, $CELL
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, $W
.else
  push $W
.endif
  $NEXT


$DEFCODE "FILL", 4, 0, FILL
  ; ( c-addr u char -- )
.ifdef FORTH_TIR
  pop $W ; u
  pop $X ; c-addr
  cmp $W, 0
  ble &__FILL_next
__FILL_loop:
  stb $X, $TOS
  inc $X
  dec $W
  bnz &__FILL_loop
__FILL_next:
  pop $TOS
.else
  pop $W ; char
  pop $X ; u
  pop $Y ; c-addr
  cmp $W, 0
  ble &__FILL_next
__FILL_loop:
  cmp $X, 0
  bz &__FILL_next
  stb $Y, $W
  inc $Y
  dec $X
  j &__FILL_loop
__FILL_next:
.endif
  $NEXT


;
; void memcpy(void *src, void *dst, u32_t length)
;
; Copy content of memory at SRC, of length of LENGTH bytes, to address DST.
; Source and destination areas should not overlap, otherwise memcpy could
; lead to unpredicted results.
;
memcpy:
  cmp r2, 0
  bz &__memcpy_quit
  push r3
__memcpy_loop:
  lb r3, r0
  stb r1, r3
  inc r0
  inc r1
  dec r2
  bnz &__memcpy_loop
  pop r3
__memcpy_quit:
  ret


;
; void memmove(void *src, void *dst, u32_t length)
;
; Copy content of memory at SRC, of length of LENGTH bytes, to address DST.
; Source and destination areas can overlap, transfer uses a temporary storage.
;
memmove:
  ; r3 - tmp ptr

  push r3
  la r3, &var_DP
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
.ifdef FORTH_TIR
  mov r2, $TOS
  pop r1
  pop r0
  pop $TOS
.else
  pop r2 ; u
  pop r1 ; addr2
  pop r0 ; addr1
.endif
  call &memmove
  $NEXT


mm_alloc:
  push r1
  ; convert number of bytes to number of pages, add 2 bytes for pages count
  add r0, $CELL
  $align_page r0
  div r0, $PAGE_SIZE
  mov r1, r0 ; save pages count
  ; call &mm_area_alloc
  stw r0, r1 ; save pages count at the beggining of the area
  add r0, $CELL ; and return the rest of the area to the caller
  pop r1
  ret


mm_free:
  push r1
  sub r0, $CELL
  lw r1, r0
  ; call &mm_area_free
  pop r1
  ret


$DEFCODE "ALLOCATE", 8, 0, ALLOCATE
  ; ( u -- a-addr ior )
  pop $W

  ;li r0, $MM_OP_UNUSED
  ;int $INT_MM
  ;mul r0, $PAGE_SIZE
  ;cmpu $W, r0
  ;bg &__ALLOCATE_oom

  mov r0, $W
  call &mm_alloc
  push r0
  push 0
  $NEXT

__ALLOCATE_oom:
  $push_true $W ; address
  $push_true $W ; 'failed' IOR
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

  ;li r0, $MM_OP_UNUSED
  ;int $INT_MM
  ;mul r0, $PAGE_SIZE
  ;cmpu $W, r0
  ;bg &__RESIZE_oom

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
  ble &__RESIZE_new_smaller

  mov r2, r3
  j &__RESIZE_copy

__RESIZE_new_smaller:
  mov r2, r4

__RESIZE_copy:
  mul r2, $PAGE_SIZE
  sub r2, $CELL

  mov r0, $X
  mov r1, r5
  call &memcpy

  mov r0, $X
  call &mm_free

  push r5
  push 0
  j &__RESIZE_next

__RESIZE_oom:
  push $X
  $push_true $W

__RESIZE_next:
  $NEXT

; - Arithmetics -------------------------------------------------------------------------

$DEFCODE "LSHIFT", 6, 0, LSHIFT
  ; ( n u -- n )
.ifdef FORTH_TIR
  pop $W
  shiftl $W, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  shiftl $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "RSHIFT", 6, 0, RSHIFT
  ; ( n u -- n )
.ifdef FORTH_TIR
  pop $W
  shiftr $W, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  shiftr $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "2*", 2, 0, TWOSTAR
  ; ( n -- n )
.ifdef FORTH_TIR
  shiftl $TOS, 1
.else
  pop $W
  shiftl $W, 1
  push $W
.endif
  $NEXT


$DEFCODE "2/", 2, 0, TWOSLASH
  ; ( n -- n )
  li $Y, 0x0000
  liu $Y, 0x8000
.ifdef FORTH_TIR
  mov $W, $TOS
  shiftr $TOS, 1
  and $W, $Y
  bz &__TWOSLASH_next
  or $TOS, $Y
__TWOSLASH_next:
.else
  pop $W
  mov $X, $W
  shiftr $W, 1
  and $X, $Y
  bz &__TWOSLASH_next
  or $W, $Y
__TWOSLASH_next:
  push $W
.endif
  $NEXT


$DEFCODE "U<", 2, 0, ULT
  ; ( a b -- flag )
.ifdef FORTH_TIR
  pop $W
  cmpu $W, $TOS
.else
  pop $W
  pop $X
  cmpu $X, $W
.endif
  bl &__CMP_true
  j &__CMP_false


$DEFCODE "U>", 2, 0, UGT
  ; ( a b -- flag )
.ifdef FORTH_TIR
  pop $W
  cmpu $W, $TOS
.else
  pop $W
  pop $X
  cmpu $X, $W
.endif
  bg &__CMP_true
  j &__CMP_false


$DEFCODE "MAX", 3, 0, MAX
  ; ( a b -- n )
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
  ble &__MIN_next
  mov $TOS, $W
.else
  pop $W
  pop $X
  cmp $W, $X
  bg &__MIN_greater
  push $X
  j &__MIN_next
__MIN_greater:
  push $W
.endif
__MIN_next:
  $NEXT


$DEFCODE "MIN", 3, 0, MIN
  ; ( a b -- n )
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
  bge &__MIN_next
  mov $TOS, $W
.else
  pop $W
  pop $X
  cmp $W, $X
  bl &__MIN_lower
  push $X
  j &__MIN_next
__MIN_lower:
  push $W
.endif
__MIN_next:
  $NEXT


$DEFCODE "ABS", 3, 0, ABS
  ; ( n -- n )
.ifdef FORTH_TIR
  cmp $TOS, 0
  bge &__ABS_next
  mul $TOS, -1
__ABS_next:
.else
  pop $W
  cmp $W, 0
  bge &__ABS_next
  mul $W, -1
__ABS_next:
  push $W
.endif
  $NEXT


; - Printing ----------------------------------------------------------------------------

  .data

  .type pno_buffer, space
  .space $PNO_BUFFER_SIZE

  .type pno_ptr, int
  .int 0

  .type pno_chars, string
  .string "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

__reset_pno_buffer:
  push r0
  push r1
  push r2
  la r0, &pno_buffer
  la r1, &pno_ptr
  add r0, $PNO_BUFFER_SIZE
  stw r1, r0
  sub r0, $PNO_BUFFER_SIZE
  li r1, $PNO_BUFFER_SIZE
  li r2, 0xBF
  call &memset
  pop r2
  pop r1
  pop r0
  ret

__pno_append_char:
  push r1
  push r2
  la r1, &pno_ptr
  lw r2, r1
  dec r2
  stb r2, r0
  stw r1, r2
  pop r2
  pop r1
  ret

__pno_append_number:
  push r1
  la r1, &pno_chars
  add r0, r1
  lb r0, r0
  pop r1
  j &__pno_append_char


$DEFCODE "<#", 2, 0, LESSNUMBERSIGN
  ; ( -- )
  call &__reset_pno_buffer
  $NEXT

$DEFCODE "#>", 2, 0, NUMBERSIGNGREATER
  ; ( xd -- c-addr u )
  la $X, &pno_ptr    ; pno_ptr addr
  lw $Y, $X          ; pno_ptr

  la $W, &pno_buffer
  add $W, $PNO_BUFFER_SIZE
  sub $W, $Y
.ifdef FORTH_TIR
  stw sp, $Y
  mov $TOS, $W
.else
  stw sp, $W
  stw sp[$CELL], $Y
.endif
  $NEXT

$DEFCODE "SIGN", 4, 0, SIGN
.ifdef FORTH_TIR
  pop r0
  swp r0, $TOS
  cmp r0, 0
.else
  pop r0
.endif
  bns &__SIGN_next
  li r0, 0x2D
  call &__pno_append_char
__SIGN_next:
  $NEXT


$DEFCODE "HOLD", 4, 0, HOLD
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
  call &__pno_append_char
  $NEXT


$DEFCODE "#", 1, 0, NUMBERSIGN
  ; ( ud1 - ud2 )
  la $W, &var_BASE
  lw $W, $W
.ifdef FORTH_TIR
  push $TOS          ; push TOS on stack so we can use pop to load it to math stack
.endif
  sis $MATH_INST_SET
  pop                ; ud1
  loadw $W           ; ud1 n
  dup2               ; ud1 n ud1 n
  umodl              ; ud1 n rem
  savew r0           ; ud1 n
  udivl              ; quot
.ifdef FORTH_TIR
  save $TOS, $X      ; split quot between TOS and stack
  sis $DUCKY_INST_SET
  push $X
.else
  push               ; just push double on stack
  sis $DUCKY_INST_SET
.else
  call &__pno_append_number
  $NEXT


$DEFCODE "#S", 2, 0, NUMBERSIGNS
  ; ( ud1 - 0 0 )
  la $W, &var_BASE
  lw $W, $W
.ifdef FORTH_TIR
  push $TOS          ; push TOS on stack so we can use pop to load it to math stack
.endif
  sis $MATH_INST_SET
  pop                ; ud1
__NUMBERSIGNS_loop:
  sis $MATH_INST_SET ; turn math inst set on at the beginning of each iteration
  loadw $W           ; ud base
  dup2               ; ud base ud base
  umodl              ; ud base rem
  savew r0           ; ud base
  udivl              ; quot
  dup                ; quot quot
  save $Y, $Z        ; quot
  sis $DUCKY_INST_SET
  call &__pno_append_number

  cmp $Y, $Z
  bnz &__NUMBERSIGNS_loop
  sis $MATH_INST_SET
  drop               ;
  sis $DUCKY_INST_SET

  push 0x00
.ifdef FORTH_TIR
  li $TOS, 0x00
.else
  push 0x00
.endif
  $NEXT


$DEFCODE ">NUMBER", 7, 0, TONUMBER
  ; ( ud1 c-addr1 u1 -- ud2 c-addr2 u2 )
.ifdef FORTH_TIR
                                  ; u1 is in TOS
  pop $W                          ; c-addr
.else
  pop $Z                          ; u1
  pop $W                          ; c-addr
.endif
  sis $MATH_INST_SET
  pop                             ;  -- ud1
  sis $DUCKY_INST_SET
  la r10, &pno_chars              ; cache char table ptr
  la r11, &var_BASE               ; cache BASE
  lw r11, r11
  mov r12, r10                    ; compute pointer to the digit right *after* the BASE reach
  add r12, r11
.ifdef FORTH_TIR
  cmp $TOS, 0                     ; check if there are any chars left
.else
  cmp $Z, 0
.endif
__TONUMBER_loop:
  bz &__TONUMBER_complete
  lb $X, $W                       ; fetch char
  mov r13, r10                    ; lookup char in table
__TONUMBER_find_char:
  lb r14, r13
  cmp r14, $X
  be &__TONUMBER_char_found       ; found
  inc r13
  cmp r13, r12                    ; if our table ptr points to the char outside the base, not found
  be &__TONUMBER_complete
  j &__TONUMBER_find_char
__TONUMBER_char_found:
  sub r13, r10                    ; char represents value (offset - PNO chars table)
  sis $MATH_INST_SET              ; add digit to accumulator
  loadw r11                       ; ud1 -- ud1 base
  mull                            ; ud1 base -- (ud1 * base)
  loadw r13                       ; (ud1 * base) -- (ud1 * base) digit
  addl                            ; (ud1 * base) digit -- (ud1 * base + digit) = ud1
  sis $DUCKY_INST_SET
  inc $W                          ; move to the next digit
.ifdef FORTH_TIR
  dec $TOS                        ; and decrement remaining chars counter
.else
  dec $Z
.endif
  j &__TONUMBER_loop
__TONUMBER_complete:
  sis $MATH_INST_SET
  push                            ; save accumulator
  sis $DUCKY_INST_SET
  push $W                         ; save string pointer
.ifdef FORTH_TIR
                                  ; counter stays in TOS
.else
  push $Z                         ; push counter
.endif
  $NEXT


$DEFCODE "U.", 2, 0, UDOT
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
  call &__UDOT
  $NEXT

__UDOT:
  ; BASE
  push r1
  la r1, &var_BASE
  lw r1, r1

  push r0 ; save r0 for mod later
  udiv r0, r1
  bz &__UDOT_print
  call &__UDOT

__UDOT_print:
  pop r0 ; restore saved number and mod it
  mod r0, r1
  cmp r0, 10
  bge &__UDOT_print_letters
  add r0, 48

__UDOT_emit:
  call &__write_stdout
  pop r1 ; restore saved r1 (BASE)
  ret

__UDOT_print_letters:
  sub r0, 10
  add r0, 65
  j &__UDOT_emit


$DEFCODE ".S", 2, 0, DOTS
.ifdef FORTH_TIR
  la $W, &var_SZ
  lw $W, $W
  sub $W, sp
  bz &__DOTS_next
  mov r0, $TOS
  call &__UDOT
  call &__SPACE
  sub $W, $CELL
  mov sp, $X
__DOTS_loop:
  bz &__DOTS_next
  lw r0, $X
  call &__UDOT
  call &__SPACE
  add $X, $CELL
  dec $W
  j &__DOTS_loop
.else
  mov $W, sp
  la $X, &var_SZ
  lw $X, $X
__DOTS_loop:
  lw r0, $W
  call &__UDOT
  call &__SPACE
  add $W, $CELL
  cmp $W, $X
  bl &__DOTS_loop
.endif
__DOTS_next:
  $NEXT


$DEFCODE "ID.", 3, 0, IDDOT
  ; ( a-addr -- )
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
  call &__IDDOT
  $NEXT

__IDDOT:
  ; void __IDDOT(void *ptr)
  ; it's just about constructing arguments for write()
  push r1
  add r0, $wr_namelen
  lb r1, r0
  inc r0
  call &writeln
  pop r1
  ret


$DEFCODE "WORDS", 5, 0, WORDS
  ; ( -- )
  call &__WORDS
  $NEXT

__WORDS:
  push r0
  push r10
  la r10, &var_LATEST
  lw r10, r10
  mov r0, r10
__WORDS_loop:
  bz &__WORDS_quit
  call &__IDDOT
  lw r10, r10
  mov r0, r10
  j &__WORDS_loop
__WORDS_quit:
  pop r10
  pop r0
  ret
