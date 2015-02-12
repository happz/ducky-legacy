; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "defs.asm"

.def DUCKY_VERSION: 0x0001

; One cell is 16 bits, 2 bytes, this is 16-bit FORTH. I hope it's clear now :)
.def CELL:               2

; This is actually 8096 - first two bytes are used by HERE_INIT
; needed for HERE inicialization. HERE_INIT's space can be then
; reused as userspace
.def USERSPACE_SIZE:   8096

; 32 cells
.def RSTACK_SIZE:        64

; Let's say the longest line can be 512 chars...
.def INPUT_BUFFER_SIZE: 512

; 32 chars should be enough for any word
.def WORD_SIZE:          32

; 32 cells, should be enough
.def RSTACK_SIZE: 64

; Some commonly used registers
.def FIP: r12
.def PSP: sp
.def RSP: r11
.def W:   r10
.def X:   r9
.def Y:   r8
.def Z:   r7

; Offsets of word header fields
.def wr_link:     0
.def wr_flags:    2
.def wr_namelen:  3
.def wr_name:     4

; Word flags
.def F_IMMED:  0x0001
.def F_HIDDEN: 0x0002

; FORTH boolean "flags"
.def FORTH_TRUE:  0xFFFF
.def FORTH_FALSE: 0x0000

; Machine interrupts
.def INT_VMDEBUG:    3
.def INT_CONIO:      4


.macro pushrsp reg:
  sub $RSP, $CELL
  stw $RSP, #reg
.end

.macro poprsp reg:
  lw #reg, $RSP
  add $RSP, $CELL
.end

.macro NEXT:
  ; FIP points to a cell with address of a Code Field,
  ; and Code Field contains address of routine

  lw $W, $FIP      ; W = address of a Code Field
  add $FIP, $CELL  ; move FIP to next cell in thread
  lw $X, $W        ; X = address of routine
  j $X
.end

.macro DEFWORD name, len, flags, label:
  .section .rodata
name_#label:
  .int link
  .set link, &name_#label
  .byte #flags
  .byte #len
  .ascii #name
#label:
  .int &DOCOL
.end

.macro DEFCODE name, len, flags, label:
  .section .rodata
name_#label:
  .int link
  .set link, &name_#label
  .byte #flags
  .byte #len
  .ascii #name
#label:
  .int &code_#label
  .text
code_#label:
.end

.macro DEFVAR name, len, flags, label, initial:
  $DEFCODE #name, #len, #flags, #label
  push &var_#label
  $NEXT

  .data
  .type var_#label, int
  .int #initial
.end

.macro DEFCONST name, len, flags, label, value:
  $DEFCODE #name, #len, #flags, #label
  push #value
  $NEXT
.end

.macro align2 reg:
  inc #reg
  and #reg, 0xFFFE
.end

.macro align4 reg, mask_reg:
  add #reg, 3
  and #reg, 0xFFFC
.end


  ; Welcome and bye messages
  .section .rodata

  .type welcome_message, string
  .string "Ducky Forth welcomes you\n\r\n\r"

  .type bye_message, string
  .string "\r\nBye.\r\n"

  .text


halt:
  ; r0 - exit code
  hlt r0


strcmp:
  ; r0: s1 addr, r1: s1 len, r2: s2 addr, r3 s2 len
  cmp r1, r3
  bne &.strcmp_neq
  bz &.strcmp_eq
  ; save working registers
  push r4 ; curr s1 char
  push r5 ; curr s2 char
.strcmp_loop:
  lb r4, r0
  lb r5, r2
  inc r0
  inc r2
  cmp r4, r5
  be &.strcmp_next
  pop r5
  pop r4
.strcmp_neq:
  li r0, 1
  ret
.strcmp_next:
  dec r1
  bnz &.strcmp_loop
  pop r5
  pop r4
.strcmp_eq:
  li r0, 0
  ret


write:
  ; r0 - ptr
  ; r1 - size
  cmp r1, r1
  bz &.__write_quit
  push r2
.__write_loop:
  lb r2, r0
  inc r0
  outb $PORT_CONIO_STDOUT, r2
  dec r1
  bnz &.__write_loop
  pop r2
.__write_quit:
  ret


writec:
  ; r0 - char
  outb $PORT_CONIO_STDOUT, r0
  ret


writes:
  ; r0 - ptr
  push r1
.__writes_loop:
  lb r1, r0
  bz &.__writes_quit
  outb $PORT_CONIO_STDOUT, r1
  inc r0
  j &.__writes_loop
.__writes_quit:
  pop r1
  ret


writeln:
  ; r0 - ptr
  ; r1 - size
  call &write
  call &write_new_line
  ret


writesln:
  ; r0 - ptr
  call &writes
  call &write_new_line
  ret


write_new_line:
  push r0
  li r0, 0xA
  outb $PORT_CONIO_STDOUT, r0
  li r0, 0xD
  outb $PORT_CONIO_STDOUT, r0
  pop r0
  ret


write_word_buffer:
  push r0
  push r1
  ; prefix
  li r0, &buffer_print_prefix
  call &writes
  ; word buffer
  li r0, &word_buffer
  li r1, &word_buffer_length
  lw r1, r1
  call &write
  ; postfix + new line
  li r0, &buffer_print_postfix
  call &writesln
  pop r1
  pop r0
  ret


main:
  ; init RSP
  li $RSP, &rstack_top

  ; save stack base
  li r0, &var_SZ
  stw r0, sp

  ; print welcome message
  li r0, &welcome_message
  call &writes

  ; and boot...
  li $FIP, &cold_start ; boot
  $NEXT


readline:
  push r0 ; &input_buffer_length
  push r1 ; input_buffer_length
  push r2 ; input_buffer
  push r3 ; current input char
  ; now init variables
  li r0, &input_buffer_length
  li r1, 0 ; clear input buffer
  li r2, &input_buffer
.__readline_loop:
  inb r3, $PORT_CONIO_STDIN
  cmp r3, 0xFF
  be &.__readline_wait_for_input
  stb r2, r3
  inc r1
  inc r2
  cmp r3, 0x0A ; nl
  be &.__readline_quit
  cmp r3, 0x0D ; cr
  be &.__readline_quit
  j &.__readline_loop
.__readline_quit:
  stw r0, r1 ; save input_buffer_length
  ; reset input_buffer_index
  li r0, &input_buffer_index
  li r1, 0
  stw r0, r1
  pop r3
  pop r2
  pop r1
  pop r0
  ret
.__readline_wait_for_input:
  ; This is a small race condition... What if new key
  ; arrives after inb and before idle? We would be stuck until
  ; the next key arrives (and it'd be Enter, nervously pressed
  ; by programmer while watching machine "doing nothing"
  idle
  j &.__readline_loop


DOCOL:
  $pushrsp $FIP
  add $W, $CELL
  mov $FIP, $W
  $NEXT


DODOES:
  ; DODES is entered in the very same way as DOCOL:
  ; X = address of Code Field routine, i.e. DODES
  ; W = address of Code Field of this word
  ;
  ; Therefore:
  ; *W       = &CF
  ; *(W + CELL) = address of behavior words
  ; *(W + 2 * CELL) = address of this word's data

  add $W, $CELL           ; W points to Param Field #0 - behavior cell
  lw $Z, $W
  bz &.__DODOES_push

  $pushrsp $FIP
  mov $FIP, $W

.__DODOES_push:
  add $W, $CELL           ; W points to Param Field #1 - payload address
  push $W
  $NEXT


  .section .rodata
cold_start:
  ;.int &BYE
  .int &QUIT


  .section .data

  .type word_buffer, space
  .space $WORD_SIZE

  .type word_buffer_length, int
  .int 0

  .type input_buffer, space
  .space $INPUT_BUFFER_SIZE

  .type input_buffer_length, int
  .int 0

  .type input_buffer_index, int
  .int 0

  .type rstack, space
  .space $RSTACK_SIZE

  .type rstack_top, int
  .int 0xFFFF

  ; User data area
  ; Keep it in separate section to keep it aligned, clean, unpoluted
  .section .userspace, rwb
  .set HERE_INIT, .
  .space $USERSPACE_SIZE

  .set link, 0

;
; Variables
;
$DEFVAR "STATE", 5, 0, STATE, 0
$DEFVAR "HERE", 4, 0, HERE, HERE_INIT
$DEFVAR "LATEST", 6, 0, LATEST, &name_BYE
$DEFVAR "S0", 2, 0, SZ, 0
$DEFVAR "BASE", 4, 0, BASE, 10
$DEFVAR ">IN", 3, 0, TOIN, 0


;
; Kernel words
;

$DEFCODE "VMDEBUGON", 9, 0, VMDEBUGON
  ; ( -- )
  li r0, 1
  int $INT_VMDEBUG
  $NEXT

$DEFCODE "VMDEBUGOFF", 10, 0, VMDEBUGOFF
  ; ( -- )
  li r0, 0
  int $INT_VMDEBUG
  $NEXT

$DEFCODE "CONIOECHOON", 11, 0, CONIOECHOON
  ; ( -- )
  li r0, 0
  li r1, 1
  int $INT_CONIO
  $NEXT

$DEFCODE "CONIOECHOOFF", 12, 0, CONIOECHOOFF
  ; ( -- )
  li r0, 0
  li r0, 0
  int $INT_CONIO
  $NEXT

$DEFCODE "INTERPRET", 9, 0, INTERPRET
  call &.__WORD

  push r6
  push r5
  li r5, &var_STATE
  lw r5, r5
  li r6, 0 ; interpret_as_lit?

  ; search dictionary
  push r0
  push r1
  call &.__FIND
  cmp r0, r0
  bz &.__INTERPRET_as_lit
  pop r6 ; pop r1
  pop r6 ; pop r0
  li r6, 0 ; restore interpret_as_lit
  mov r1, r0
  add r1, $wr_flags
  call &.__TCFA
  lb r1, r1
  and r1, $F_IMMED
  cmp r1, r1
  bnz &.__INTERPRET_execute
  j &.__INTERPRET_state_check

.__INTERPRET_as_lit:
  pop r1
  pop r0
  inc r6
  call &.__NUMBER
  ; r0 - number, r1 - unparsed chars
  cmp r1, r1
  bnz &.__INTERPRET_parse_error
  mov r1, r0  ; save number
  li r0, &LIT ; and replace with LIT

.__INTERPRET_state_check:
  cmp r5, r5
  bz &.__INTERPRET_execute
  call &.__COMMA ; append r0 (aka word) to current definition
  cmp r6, r6
  bz &.__INTERPRET_next ; if not LIT, just leave
  mov r0, r1
  call &.__COMMA ; append r0 (aka number) to current definition
  j &.__INTERPRET_next

.__INTERPRET_execute:
  cmp r6, r6
  bnz &.__INTERPRET_execute_lit
  pop r5
  pop r6
  mov $W, r0
  lw $X, r0
  j $X

.__INTERPRET_execute_lit:
  pop r5
  pop r6
  push r1
  $NEXT

.__INTERPRET_parse_error:
  ; error message
  li r0, &parse_error_msg
  call &writes
  ; input buffer label
  li r0, &parse_error_input_buffer_prefix
  call &writes
  ; prefix
  li r0, &buffer_print_prefix
  call &writes
  ; input buffer
  li r0, &input_buffer
  li r1, &input_buffer_length
  lw r1, r1
  call &write
  ; new line
  li r0, 0
  li r1, 0
  call &writeln
  ; word buffer label
  li r0, &parse_error_word_buffer_prefix
  call &writes
  call &write_word_buffer
  call &halt

.__INTERPRET_next:
  pop r5
  pop r6
  $NEXT

  .section .rodata

  .type parse_error_msg, string
  .string "\r\nPARSE ERROR!\r\n"

  .type parse_error_input_buffer_prefix, string
  .string "Input buffer: "

  .type parse_error_word_buffer_prefix, string
  .string "Word buffer: "

  .type buffer_print_prefix, string
  .string ">>>"

  .type buffer_print_postfix, string
  .string "<<<"

$DEFCODE ">IN", 3, 0, TOIN
  push &input_buffer_index
  $NEXT


$DEFCODE "KEY", 3, 0, KEY
  ; ( -- n )
  call &.__KEY
  push r0
  $NEXT

.__KEY:
  ; r0 - input char
  push r1 ; &input_buffer_length
  push r2 ; input_buffer_length
  push r3 ; &input_buffer_index
  push r4 ; input_buffer_index
  push r5 ; index_buffer ptr
  li r1, &input_buffer_length
  lw r2, r1
  li r3, &input_buffer_index
  lw r4, r3
  cmp r2, r4
  be &.__KEY_read_line
.__KEY_read_char:
  ; get char ptr
  li r5, &input_buffer
  add r5, r4
  ; read char
  lb r0, r5
  ; and update vars
  inc r4
  stw r3, r4
  pop r5
  pop r4
  pop r3
  pop r2
  pop r1
  ret
.__KEY_read_line:
  call &readline
  ; reload our vars
  lw r2, r1
  lw r4, r3
  j &.__KEY_read_char


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
  pop r0
  call &.__EMIT
  $NEXT

.__EMIT:
  outb $PORT_CONIO_STDOUT, r0
  ret


$DEFCODE "TYPE", 4, 0, TYPE
  ; ( address length -- )
  pop r1
  pop r0
  call &write
  $NEXT


$DEFCODE "WORD", 4, 0, WORD
  ; ( -- address length )
  call &.__WORD
  push r0
  push r1
  $NEXT

.__WORD:
  call &.__KEY
  ; if key's backslash, comment starts - skip it, to the end of line
  cmp r0, 0x5C ; backslash
  be &.__WORD_skip_comment
  ; if key's lower or eaqual to space, it's considered as a white space, and ignored.
  ; this removes leading white space
  cmp r0, 0x20
  ble &.__WORD
  li r1, &word_buffer
.__WORD_store_char:
  stb r1, r0
  inc r1
  call &.__KEY
  cmp r0, 0x20 ; space
  bg &.__WORD_store_char
  sub r1, &word_buffer
  ; save word length for debugging purposes
  push r2
  li r2, &word_buffer_length
  stw r2, r1
  pop r2
  li r0, &word_buffer
  ; call &write_word_buffer
  ret
.__WORD_skip_comment:
  call &.__KEY
  cmp r0, 0x0A ; nl
  be &.__WORD
  cmp r0, 0x0D ; cr
  be &.__WORD
  j &.__WORD_skip_comment


$DEFCODE "SOURCE", 6, 0, SOURCE
  ; ( address length )
  li $W, &input_buffer
  push $W
  li $W, &input_buffer_length
  lw $W, $W
  push $W
  $NEXT


$DEFCODE "NUMBER", 6, 0, NUMBER
  ; ( address length -- number unparsed_chars )
  pop r1
  pop r0
  call &.__NUMBER
  push r0
  push r1
  $NEXT


.__NUMBER:
  cmp r1, r1
  bz &.__NUMBER_quit_noclean
  ; save working registers
  push r2 ; BASE
  push r3 ; char ptr
  push r4 ; current char
  ; set up working registers
  li r2, &var_BASE
  lw r2, r2
  mov r3, r0
  li r0, 0
  ; read first char and check if it's minus
  lb r4, r3
  inc r3
  dec r1
  ; 0 on stack means non-negative number
  push 0
  cmp r4, 0x2D
  bne &.__NUMBER_convert_digit
  pop r4 ; it's minus, no need to preserve r4, so pop 0 from stack...
  push 1 ; ... and push 1 to indicate negative number
  ; if there are no remaining chars, we got only '-' - that's bad, quit
  cmp r1, r1
  bnz &.__NUMBER_loop
  pop r1 ; 1 was on stack to signal negative number, reuse it as error message
.__NUMBER_quit:
  pop r4
  pop r3
  pop r2
.__NUMBER_quit_noclean:
  ret

.__NUMBER_loop:
  cmp r1, r1
  bz &.__NUMBER_negate

  lb r4, r3
  inc r3
  dec r1

.__NUMBER_convert_digit:
  ; if char is lower than '0' then it's bad - quit
  sub r4, 0x30
  bs &.__NUMBER_fail
  ; if char is lower than 10, it's a digit, convert it according to base
  cmp r4, 10
  bl &.__NUMBER_check_base
  ; if it's outside the alphabet, it's bad - quit
  sub r4, 17 ; 'A' - '0' = 17
  bs &.__NUMBER_fail
  add r4, 10

.__NUMBER_check_base:
  ; if digit is bigger than base, it's bad - quit
  cmp r4, r2
  bge &.__NUMBER_fail

  mul r0, r2
  add r0, r4
  j &.__NUMBER_loop

.__NUMBER_fail:
  li r1, 1

.__NUMBER_negate:
  pop r2 ; BASE no longer needed, use its register
  cmp r2, r2
  bz &.__NUMBER_quit
  not r0
  j &.__NUMBER_quit


$DEFCODE "FIND", 4, 0, FIND
  ; ( address length -- address )
  pop r1
  pop r0
  call &.__FIND
  push r0
  $NEXT

.__FIND:
  ; r0 - address
  ; r1 - length
  ; save working registers
  push r2 ; word ptr

  li r2, &var_LATEST
  lw r2, r2

.__FIND_loop:
  cmp r2, r2
  bz &.__FIND_fail

  ; prepare call of strcmp
  push r0
  push r1
  push r2
  push r3

  mov r3, r2
  add r3, $wr_namelen
  lb r3, r3
  add r2, $wr_name

  call &strcmp
  cmp r0, 0
  be &.__FIND_success
  pop r3
  pop r2
  pop r1
  pop r0
  lw r2, r2 ; load link content
  j &.__FIND_loop
.__FIND_success:
  pop r3 ; this one we used just for calling strcmp
  pop r2
  pop r1
  pop r0
  mov r0, r2
  pop r2
  ret
.__FIND_fail:
  pop r2
  li r0, 0
  ret


$DEFCODE "'", 1, 0, TICK
  lw $W, $FIP
  push $W
  add $FIP, $CELL
  $NEXT


$DEFCODE ">CFA", 4, 0, TCFA
  ; ( address -- address )
  pop r0
  call &.__TCFA
  push r0
  $NEXT

.__TCFA:
  add r0, $wr_namelen
  push r1
  lb r1, r0
  inc r0
  add r0, r1
  $align2 r0
  pop r1
  ret


$DEFWORD ">DFA", 4, 0, TDFA
  .int &TCFA
  .int &INCR2
  .int &EXIT


$DEFCODE "LIT", 3, 0, LIT
  lw $W, $FIP
  push $W
  add $FIP, $CELL
  $NEXT


$DEFCODE "HEADER,", 7, 0, HEADER_COMMA
  pop r1 ; length
  pop r0 ; address
  call &.__HEADER_COMMA
  $NEXT

.__HEADER_COMMA:
  ; save working registers
  push r2 ; HERE address
  push r3 ; HERE value
  push r4 ; LATEST address
  push r5 ; LATEST value
  push r6 ; flags/length
  push r7 ; current word char
  ; init registers
  li r2, &var_HERE
  lw r3, r2
  li r4, &var_LATEST
  lw r5, r4
  ; store LATEST as a link value of new word
  stw r3, r5
  mov r5, r3
  stw r4, r5
  ; and move HERE to next cell
  add r3, 2
  ; save flags
  li r6, 0
  stb r3, r6
  inc r3
  ; save unaligned length ...
  stb r3, r1
  inc r3
  ; but shift HERE to next aligned address
  $align2 r3
  ; copy word name, using its original length
  mov r6, r1
.__HEADER_COMMA_loop:
  lb r7, r0
  stb r3, r7
  inc r3
  inc r0
  dec r6
  bnz &.__HEADER_COMMA_loop
  ; align HERE - this will "add" padding byte to name automagicaly
  $align2 r3
  ; save vars
  stw r2, r3 ; HERE
  stw r4, r5 ; LATEST
  ; restore working registers
  pop r7
  pop r6
  pop r5
  pop r4
  pop r3
  pop r2
  ret


$DEFCODE ",", 1, 0, COMMA
  pop r0
  call &.__COMMA
  $NEXT

.__COMMA:
  push r1 ; HERE address
  push r2 ; HERE value
  li r1, &var_HERE
  lw r2, r1
  stw r2, r0
  add r2, 2
  stw r1, r2
  pop r2
  pop r1
  ret


$DEFCODE "[", 1, $F_IMMED, LBRAC
  li $W, 0
  li $X, &var_STATE
  stw $X, $W
  $NEXT


$DEFCODE "]", 1, 0, RBRAC
  li $W, 1
  li $X, &var_STATE
  stw $X, $W
  $NEXT


$DEFWORD ":", 1, 0, COLON
  .int &WORD
  .int &HEADER_COMMA
  .int &LIT
  .int &DOCOL
  .int &COMMA
  .int &LATEST
  .int &FETCH
  .int &HIDDEN
  .int &RBRAC
  .int &EXIT


$DEFWORD ";", 1, $F_IMMED, SEMICOLON
  .int &LIT
  .int &EXIT
  .int &COMMA
  .int &LATEST
  .int &FETCH
  .int &HIDDEN
  .int &LBRAC
  .int &EXIT


$DEFCODE "IMMEDIATE", 9, $F_IMMED, IMMEDIATE
  li $W, &var_LATEST
  lw $X, $W
  add $X, $wr_flags
  lb $Y, $X
  xor $Y, $F_IMMED
  stb $X, $Y
  $NEXT


$DEFCODE "HIDDEN", 6, 0, HIDDEN
  ; ( word_address -- )
  pop $X
  add $X, $wr_flags
  lb $W, $X
  xor $W, $F_HIDDEN
  stb $X, $W
  $NEXT


$DEFCODE "BRANCH", 6, 0, BRANCH
  ; ( -- )
  lw $W, $FIP
  add $FIP, $W
  $NEXT


$DEFCODE "0BRANCH", 7, 0, ZBRANCH
  ; ( n -- )
  pop $W
  cmp $W, $W
  bz &code_BRANCH
  add $FIP, $CELL
  $NEXT


$DEFWORD "QUIT", 4, 0, QUIT
  .int &RZ
  .int &RSPSTORE
  .int &INTERPRET
  .int &BRANCH
  .int -4


$DEFWORD "HIDE", 4, 0, HIDE
  .int &WORD
  .int &FIND
  .int &HIDDEN
  .int &EXIT


$DEFCODE "EXIT", 4, 0, EXIT
  $poprsp $FIP
  $NEXT


;
; Comparison ops
;

.__CMP_true:
  push $FORTH_TRUE
  $NEXT

.__CMP_false:
  push $FORTH_FALSE
  $NEXT

$DEFCODE "=", 1, 0, EQU
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  be &.__CMP_true
  j &.__CMP_false


$DEFCODE "<>", 2, 0, NEQU
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  bne &.__CMP_true
  j &.__CMP_false


$DEFCODE "0=", 2, 0, ZEQU
  ; ( n -- n )
  pop $W
  cmp $W, 0
  bz &.__CMP_true
  j &.__CMP_false


$DEFCODE "0<>", 3, 0, ZNEQU
  ; ( n -- n )
  pop $W
  cmp $W, 0
  bnz &.__CMP_true
  j &.__CMP_false


$DEFCODE "<", 1, 0, LT
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $X, $W
  bl &.__CMP_true
  j &.__CMP_false


$DEFCODE ">", 1, 0, GT
  pop $W
  pop $X
  cmp $X, $W
  bg &.__CMP_true
  j &.__CMP_false


$DEFCODE "<=", 2, 0, LE
  pop $W
  pop $X
  cmp $X, $W
  ble &.__CMP_true
  j &.__CMP_false


$DEFCODE ">=", 2, 0, GE
  pop $W
  pop $X
  cmp $X, $W
  bge &.__CMP_true
  j &.__CMP_false


$DEFCODE "0<", 2, 0, ZLT
  ; ( n -- flag )
  ; flag is true if and only if n is less than zero
  pop $W
  cmp $W, 0
  bl &.__CMP_true
  j &.__CMP_false


$DEFCODE "0>", 2, 0, ZGT
  ; ( n -- flag )
  ; flag is true if and only if n is greater than zero
  pop $W
  cmp $W, 0
  bg &.__CMP_true
  j &.__CMP_false


$DEFCODE "0<=", 3, 0, ZLE
  pop $W
  cmp $W, 0
  ble &.__CMP_true
  j &.__CMP_false


$DEFCODE "0>=", 3, 0, ZGE
  pop $W
  cmp $W, 0
  bge &.__CMP_true
  j &.__CMP_false

$DEFCODE "?DUP", 4, 0, QDUP
  pop $W
  cmp $W, 0
  bnz &.__QDUP_nonzero
  push 0
  j &.__QDUP_next
.__QDUP_nonzero:
  push $W
  push $W
.__QDUP_next:
  $NEXT


;
; Arthmetic operations
;
$DEFCODE "+", 1, 0, ADD
  ; ( a b -- a+b )
  pop $W
  pop $X
  add $X, $W
  push $X
  $NEXT


$DEFCODE "-", 1, 0, SUB
  ; ( a b -- a-b )
  pop $W
  pop $X
  sub $X, $W
  push $X
  $NEXT


$DEFCODE "1+", 2, 0, INCR
  ; ( a -- a+1 )
  pop $W
  inc $W
  push $W
  $NEXT


$DEFCODE "1-", 2, 0, DECR
  ; ( a -- a-1 )
  pop $W
  dec $W
  push $W
  $NEXT


$DEFCODE "2+", 2, 0, INCR2
  ; ( a -- a+2 )
  pop $W
  add $W, 2
  push $W
  $NEXT


$DEFCODE "2-", 2, 0, DECR2
  ; ( a -- a-2 )
  pop $W
  sub $W, 2
  push $W
  $NEXT


$DEFCODE "4+", 2, 0, INCR4
  ; ( a -- a+4 )
  pop $W
  add $W, 4
  push $W
  $NEXT


$DEFCODE "4-", 2, 0, DECR4
  ; ( a -- a-4 )
  pop $W
  sub $W, 4
  push $W
  $NEXT


$DEFCODE "*", 1, 0, MUL
  ; ( a b -- a*b )
  pop $W
  pop $X
  mul $X, $W
  push $X
  $NEXT


$DEFCODE "/", 1, 0, DIV
  ; ( a b -- <a / b> )
  pop $W
  pop $X
  div $X, $W
  push $X
  $NEXT


$DEFCODE "MOD", 1, 0, MOD
  ; ( a b -- <a % b> )
  pop $W
  pop $X
  mod $X, $W
  push $X
  $NEXT


$DEFCODE "/MOD", 4, 0, DIVMOD
  ; ( a b -- <a % b> <a / b> )
  pop $W
  pop $X
  mov $Y, $X
  mod $X, $W
  div $Y, $W
  push $X
  push $Y
  $NEXT


$DEFCODE "AND", 3, 0, AND
  pop $W
  pop $X
  and $X, $W
  push $X
  $NEXT


$DEFCODE "OR", 2, 0, OR
  pop $W
  pop $X
  or $X, $W
  push $X
  $NEXT


$DEFCODE "XOR", 3, 0, XOR
  pop $W
  pop $X
  xor $X, $W
  push $X
  $NEXT


$DEFCODE "INVERT", 6, 0, INVERT
  pop $W
  not $W
  push $W
  $NEXT


;
; Parameter stack operations
;

$DEFCODE "DROP", 4, 0, DROP
  ; ( n -i- )
  pop $W
  $NEXT


$DEFCODE "SWAP", 4, 0, SWAP
  ; ( a b -- b a )
  pop $W
  pop $X
  push $W
  push $X
  $NEXT


$DEFCODE "DUP", 3, 0, DUP
  ; ( a -- a a )
  pop $W
  push $W
  push $W
  $NEXT


$DEFCODE "OVER", 4, 0, OVER
  ; ( a b -- a b a )
  pop $W
  pop $X
  push $X
  push $W
  push $X
  $NEXT


$DEFCODE "ROT", 3, 0, ROT
  ; ( a b c -- b c a )
  pop $W
  pop $X
  pop $Y
  push $X
  push $W
  push $Y
  $NEXT


$DEFCODE "-ROT", 4, 0, NROT
  ; ( a b c -- c a b )
  pop $W
  pop $X
  pop $Y
  push $W
  push $Y
  push $X
  $NEXT


$DEFCODE "2DROP", 5, 0, TWODROP
  ; ( n n -- )
  pop $W
  pop $W
  $NEXT


$DEFCODE "2DUP", 4, 0, TWODUP
  ; ( a b -- a b a b )
  pop $W
  pop $X
  push $X
  push $W
  push $X
  push $W
  $NEXT


$DEFCODE "2SWAP", 5, 0, TWOSWAP
  ; ( a b c d -- c d a b )
  pop $W
  pop $X
  pop $Y
  pop $Z
  push $X
  push $W
  push $Z
  push $Y
  $NEXT


;
; Input and output
;

$DEFCODE "CHAR", 4, 0, CHAR
  ; ( -- n )
  call &.__WORD
  lb $W, r0 ; load the first character of next word into W...
  push $W
  $NEXT


$DEFCODE "[CHAR]", 6, 0, BRACKETCHAR
  j &code_CHAR


;
; Return stack
;

$DEFCODE ">R", 2, 0, TOR
  pop $W
  $pushrsp $W
  $NEXT


$DEFCODE "R>", 2, 0, FROMR
  $poprsp $W
  push $W
  $NEXT


$DEFCODE "RSP@", 4, 0, RSPFETCH
  push $RSP
  $NEXT


$DEFCODE "RSP!", 4, 0, RSPSTORE
  pop $RSP
  $NEXT


$DEFCODE "RDROP", 5, 0, RDOP
  $poprsp $W
  $NEXT


$DEFCODE "R@", 2, 0, RFETCH
  ; ( -- x ) ( R:  x -- x )
  lw $W, $RSP
  push $W
  $NEXT


;
; Parameter stack
;

$DEFCODE "DSP@", 4, 0, DSPFETCH
  push sp
  $NEXT


$DEFCODE "DSP!", 4, 0, DSPSTORE
  pop sp
  $NEXT


;
; Memory operations
;
$DEFCODE "!", 1, 0, STORE
  ; ( data address -- )
  pop $W
  pop $X
  stw $W, $X
  $NEXT


$DEFCODE "@", 1, 0, FETCH
  ; ( address -- n )
  pop $W
  lw $W, $W
  push $W
  $NEXT


$DEFCODE "+!", 2, 0, ADDSTORE
  ; ( amount address -- )
  pop $W
  pop $X
  lw $Y, $W
  add $Y, $X
  stw $W, $Y
  $NEXT


$DEFCODE "-!", 2, 0, SUBSTORE
  ; ( amount address -- )
  pop $W
  pop $X
  lw $Y, $W
  sub $Y, $X
  stw $W, $Y
  $NEXT


$DEFCODE "C!", 2, 0, STOREBYTE
  ; ( data address -- )
  pop $W
  pop $X
  stb $W, $X
  $NEXT


$DEFCODE "C@", 2, 0, FETCHBYTE
  ; ( address -- n )
  pop $W
  lb $W, $W
  push $W
  $NEXT


;
; Strings
;

$DEFCODE "LITSTRING", 9, 0, LITSTRING
  lw $W, $FIP
  add $FIP, $CELL
  push $FIP ; push address
  push $W   ; push size
  add $FIP, $W
  $align2 $FIP
  $NEXT


$DEFCODE "TELL", 4, 0, TELL
  ; ( address size -- )
  pop r1
  pop r0
  call &write
  $NEXT


;
; Loop helpers
;

; %eax => $W
; %edx => $X

$DEFCODE "(DO)", 4, 0, PAREN_DO
  ; ( control index -- )
  pop $W ; index
  pop $X ; control
  $pushrsp $X ; control
  $pushrsp $W ; index
  $NEXT


$DEFCODE "(LOOP)", 6, 0, PAREN_LOOP
  $poprsp $W ; index
  $poprsp $X ; control
  inc $W
  cmp $W, $X
  be &.__PAREN_LOOP_next
  $pushrsp $X
  $pushrsp $W
  lw $W, $FIP
  add $FIP, $W
  $NEXT
.__PAREN_LOOP_next:
  add $FIP, $CELL
  $NEXT


$DEFCODE "UNLOOP", 6, 0, UNLOOP
  add $RSP, 4
  $NEXT


$DEFCODE "I", 1, 0, I
  lw $W, $RSP
  push $W
  $NEXT


$DEFCODE "J", 1, 0, J
  lw $W, $RSP[4]
  push $W
  $NEXT


;
; Constants
;
$DEFCONST "VERSION", 7, 0, VERSION, $DUCKY_VERSION
$DEFCONST "R0", 2, 0, RZ, &rstack_top
$DEFCONST "DOCOL", 5, 0, __DOCOL, &DOCOL
$DEFCONST "F_IMMED", 7, 0, __F_IMMED, $F_IMMED
$DEFCONST "F_HIDDEN", 8, 0, __F_HIDDEN, $F_HIDDEN
$DEFCONST "TRUE", 4, 0, TRUE, 0xFFFF
$DEFCONST "FALSE", 5, 0, FALSE, 0x0000
$DEFCONST "DODOES", 6, 0, __DODOES, &DODOES


; Include non-kernel words
.include "forth/ducky-forth-words.asm"


;
; The last command - if it's not the last one, modify initial value of LATEST
;
$DEFCODE "BYE", 3, 0, BYE
  li r0, &bye_message
  call &writes

  call &halt



;
; Test stuff
;

  .section .test_rodata, r
  .section .test_data, rw
  .section .test_text, rx

.macro TEST_NUMBER id, label, str, len, ret0, ret1:
  .section .test_rodata

  .type TEST_label_#id, string
  .string #label

  .type TEST_buffer_#id, string
  .string #str

  .section .test_text

.__TEST_NUMBER_#id:
  li r0, &TEST_buffer_#id
  li r1, #len
  call &.__NUMBER
  cmp r0, #ret0
  bne &.__TEST_fail_#id
  cmp r1, #ret1
  bne &.__TEST_fail_#id
  j &.__TEST_pass_#id
.__TEST_fail_#id:
  li r0, &TEST_label_#id
  call &test_fail
.__TEST_pass_#id:
  nop
.end

.macro TEST_MSG name, label:
  .section .test_rodata
  .type TEST_MSG_#name, string
  .string #label
.end


  $TEST_MSG EOL, "\\r\\n"
  $TEST_MSG FAILED, "Test failed: "
  $TEST_MSG PASSED, "Tests passed"

  $TEST_MSG NUMBER1, "NUMBER"
  $TEST_MSG SWAP1, "SWAP1"

  .section .test_text


test_fail:
  push r0
  li r0, &TEST_MSG_FAILED
  call &writes
  pop r0
  call &writes
  li r0, &TEST_MSG_EOL
  call &writes
  call &halt


tests_main:
  nop

  ;
  ; NUMBER
  ;
  $TEST_NUMBER  100, "number-0",     "0",     1,         0, 0
  $TEST_NUMBER  101, "number-1",     "1",     1,         1, 0
  $TEST_NUMBER  102, "number-10",    "10",    2,        10, 0
  $TEST_NUMBER  103, "number-11",    "11",    2,        11, 0
  $TEST_NUMBER  104, "number-0=",    "0=",    2,         0, 1
  $TEST_NUMBER  105, "number-759",   "759",   3,       759, 0
  $TEST_NUMBER  106, "number-16021", "16021", 5,     16021, 0
  $TEST_NUMBER  107, "number-12",    "12+",   3,        12, 1
  $TEST_NUMBER  108, "number--1",    "-1",    2,    0xFFFE, 0

  li r0, &TEST_MSG_PASSED
  call &writes
  li r0, &TEST_MSG_EOL
  call &writes

  li r0, 0
  int 0

