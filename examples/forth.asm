; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.def DUCKY_VERSION: 0x0001

.def FIP: r12
.def PSP: sp
.def RSP: r11
.def W:   r10
.def X:   r9
.def Y:   r8
.def TOS: r7

.def PORT_STDIN:  0x100
.def PORT_STDOUT: 0x100
.def PORT_STDERR: 0x101

; 32 cells, should be enough
.def RSTACK_SIZE: 64

.def wr_link:     0
.def wr_flags:    2
.def wr_namelen:  3
.def wr_name:     4

.def F_IMMED:  0x0001
.def F_HIDDEN: 0x0002

.macro pushrsp reg:
  sub $RSP, 2
  stw $RSP, #reg
.end

.macro poprsp reg:
  lw #reg, $RSP
  add $RSP, 2
.end

.macro NEXT:
  lw $W, $FIP
  add $FIP, 2
  lw $X, $W
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
  push $TOS
  li $TOS, &var_#label
  $NEXT

  .data
  .type var_#label, int
  .int #initial
.end

.macro DEFCONST name, len, flags, label, value:
  $DEFCODE #name, #len, #flags, #label
  push $TOS
  li $TOS, #value
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


  ; RSTACK
  .data

  .type rstack, space
  .space 64

  .type rstack_top, int
  .int 0xFFFF

  ; Welcome and bye messages
  .section .rodata

  .type welcome_message, string
  .string "Ducky Forth welcomes you\n\r\n\r"

  .type bye_message, string
  .string "\r\nBye.\r\n"

  .text


halt:
  ; r0 - exit code
  int 0


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
  outb $PORT_STDOUT, r2
  dec r1
  bnz &.__write_loop
  pop r2
.__write_quit:
  ret


writes:
  ; r0 - ptr
  push r1
.__writes_loop:
  lb r1, r0
  bz &.__writes_quit
  outb $PORT_STDOUT, r1
  inc r0
  j &.__writes_loop
.__writes_quit:
  pop r1
  ret


writeln:
  ; r0 - ptr
  ; r1 - size
  call &write
  push r2
  li r2, 0xA
  outb $PORT_STDOUT, r2
  li r2, 0xD
  outb $PORT_STDOUT, r2
  pop r2
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


DOCOL:
  $pushrsp $FIP
  add $W, 2
  mov $FIP, $W
  $NEXT


  .section .rodata
cold_start:
  ;.int &BYE
  .int &QUIT


  .section .userspace, rw
__HERE_INIT:
  .space 8096


  .set link, 0

;
; Variables
;
$DEFVAR "STATE", 5, 0, STATE, 0
$DEFVAR "HERE", 4, 0, HERE, &__HERE_INIT
$DEFVAR "LATEST", 6, 0, LATEST, &name_BYE
$DEFVAR "S0", 2, 0, SZ, 0
$DEFVAR "BASE", 4, 0, BASE, 10


;
; Kernel words
;

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
  push r1
  j &.__INTERPRET_next

.__INTERPRET_parse_error:
  ; print error message
  li r0, &parse_error_msg
  li r1, &parse_error_msg_end
  sub r1, &parse_error_msg
  call &writeln
  ; print input buffer
  li r0, &word_buffer
  li r1, &word_buffer_length
  lw r1, r1
  call &writeln

  call &halt

.__INTERPRET_next:
  pop r5
  pop r6
  $NEXT

  .section .rodata

  .type parse_error_msg, ascii
  .ascii "\r\nPARSE ERROR!"

  .type parse_error_msg_end, int
  .int 0


$DEFCODE "KEY", 3, 0, KEY
  ; ( -- n )
  call &.__KEY
  push $TOS
  mov $TOS, r0
  $NEXT

.__KEY:
.__KEY_read_input:
  inb r0, $PORT_STDIN
  cmp r0, 0xFF
  be &.__KEY_wait_for_input
  ret
.__KEY_wait_for_input:
  idle
  j &.__KEY_read_input


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
  mov r0, $TOS
  pop $TOS
  call &.__EMIT
  $NEXT

.__EMIT:
  outb $PORT_STDOUT, r0
  ret


$DEFCODE "WORD", 4, 0, WORD
  ; ( -- address length )
  call &.__WORD
  push $TOS
  push r0
  mov $TOS, r1
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
  ret
.__WORD_skip_comment:
  call &.__KEY
  cmp r0, 0x0A ; nl
  be &.__WORD
  cmp r0, 0x0D ; cr
  be &.__WORD
  j &.__WORD_skip_comment

  .data
  .type word_buffer, space
  .space 32

  .type word_buffer_length, int
  .int 0

$DEFCODE "NUMBER", 6, 0, NUMBER
  ; ( address length -- number unparsed_chars )
  pop r0
  mov r1, $TOS
  call &.__NUMBER
  push $TOS
  push r0
  mov $TOS, r1
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
  ; 0 on stack means non-negative number
  push 0
  cmp r4, 0x2D
  bne &.__NUMBER_convert_digit
  pop r4
  push 1
  dec r1
  bnz &.__NUMBER_add_digit
  pop r1 ; 1 was on stack to signal negative number, reuse it as error message
.__NUMBER_quit:
  pop r4
  pop r3
  pop r2
.__NUMBER_quit_noclean:
  ret
.__NUMBER_add_digit:
  mul r0, r2
  lb r4, r3
  inc r3
.__NUMBER_convert_digit:
  sub r4, 0x30
  bl &.__NUMBER_negate
  cmp r4, 10
  bl &.__NUMBER_check_base
  sub r4, 17 ; 'A' - '0' = 17
  bl &.__NUMBER_negate
  add r4, 10
.__NUMBER_check_base:
  cmp r4, r2
  bge &.__NUMBER_negate
  add r0, r4
  dec r1
  bnz &.__NUMBER_add_digit
.__NUMBER_negate:
  pop r2 ; BASE no longer needed, use its register
  cmp r2, r2
  bz &.__NUMBER_quit
  not r0
  j &.__NUMBER_quit


$DEFCODE "FIND", 4, 0, FIND
  ; ( address length -- address )
  pop r0
  mov r1, $TOS
  call &.__FIND
  mov $TOS, r0
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
  add $FIP, 2
  push $TOS
  lw $TOS, $FIP
  $NEXT


$DEFCODE ">CFA", 4, 0, TCFA
  ; ( address -- address )
  mov r0, $TOS
  call &.__TCFA
  mov $TOS, r0
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
  add $FIP, 2
  push $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "CREATE", 6, 0, CREATE
  ; ( address length -- )
  pop r0
  mov r1, $TOS
  pop $TOS

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
.__CREATE_loop:
  lb r7, r0
  stb r3, r7
  inc r3
  inc r0
  dec r6
  bnz &.__CREATE_loop
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
  $NEXT


$DEFCODE ",", 1, 0, COMMA
  mov r0, $TOS
  pop $TOS
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
  .int &CREATE
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
  add $TOS, $wr_flags
  lb $W, $TOS
  xor $W, $F_HIDDEN
  stb $TOS, $W
  pop $TOS
  $NEXT

$DEFCODE "BRANCH", 6, 0, BRANCH
  lw $W, $FIP
  add $FIP, $W
  $NEXT


$DEFCODE "0BRANCH", 7, 0, ZBRANCH
  mov $W, $TOS
  pop $TOS
  cmp $W, $W
  bz &code_BRANCH
  add $FIP, 2
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
; Arthmetic operations
;
$DEFCODE "+", 1, 0, ADD
  ; ( a b -- a+b )
  pop $W
  add $TOS, $W
  $NEXT


$DEFCODE "-", 1, 0, SUB
  ; ( a b -- a-b )
  pop $W
  sub $W, $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "1+", 2, 0, INCR
  ; ( a -- a+1 )
  inc $TOS
  $NEXT


$DEFCODE "1-", 2, 0, DECR
  ; ( a -- a-1 )
  dec $TOS
  $NEXT


$DEFCODE "2+", 2, 0, INCR2
  ; ( a -- a+2 )
  add $TOS, 2
  $NEXT


$DEFCODE "2-", 2, 0, DECR2
  ; ( a -- a-2 )
  sub $TOS, 2
  $NEXT


$DEFCODE "4+", 2, 0, INCR4
  ; ( a -- a+4 )
  add $TOS, 4
  $NEXT


$DEFCODE "4-", 2, 0, DECR4
  ; ( a -- a-4 )
  sub $TOS, 4
  $NEXT


$DEFCODE "*", 1, 0, MUL
  ; ( a b -- a*b )
  pop $W
  mul $TOS, $W
  $NEXT


$DEFCODE "/", 1, 0, DIV
  ; ( a b -- b/a )
  pop $W
  div $TOS, $W
  $NEXT


$DEFCODE "MOD", 1, 0, MOD
  ; ( a b -- b%a )
  pop $W
  mod $TOS, $W
  $NEXT


$DEFCODE "/MOD", 4, 0, DIVMOD
  ; ( a b -- b/a b%a )
  pop $W
  mov $X, $TOS
  div $X, $W
  mod $TOS, $W
  push $X
  $NEXT

;
; Parameter stack operations
;

$DEFCODE "DROP", 4, 0, DROP
  ; ( n -- )
  pop $TOS
  $NEXT


$DEFCODE "SWAP", 4, 0, SWAP
  ; ( a b -- b a )
  pop $W
  push $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "DUP", 3, 0, DUP
  ; ( a b -- a b b )
  push $TOS
  $NEXT


$DEFCODE "OVER", 4, 0, OVER
  ; ( a b -- a b a )
  pop $W
  push $W
  push $TOS
  mov $TOS, $W
  $NEXT


;
; Input and output
;

$DEFCODE "CHAR", 4, 0, CHAR
  ; ( -- n )
  call &.__WORD
  push $TOS
  lb $TOS, r0 ; load the first character of next word into r0...
  $NEXT


;
; Return stack
;

$DEFCODE ">R", 2, 0, TOR
  $pushrsp $TOS
  pop $TOS
  $NEXT

$DEFCODE "R>", 2, 0, FROMR
  push $TOS
  $poprsp $TOS
  $NEXT

$DEFCODE "RSP@", 4, 0, RSPFETCH
  push $TOS
  mov $TOS, $RSP
  $NEXT

$DEFCODE "RSP!", 4, 0, RSPSTORE
  mov $RSP, $TOS
  pop $TOS
  $NEXT

$DEFCODE "RDROP", 5, 0, RDOP
  $poprsp $W
  $NEXT


;
; Memory operations
;
$DEFCODE "!", 1, 0, STORE
  ; ( data address -- )
  pop $W
  stw $TOS, $W
  pop $TOS
  $NEXT

$DEFCODE "@", 1, 0, FETCH
  ; ( address -- n )
  lw $TOS, $TOS
  $NEXT

$DEFCODE "+!", 2, 0, ADDSTORE
  ; ( amount address -- )
  pop $W
  lw $X, $TOS
  add $X, $W
  stw $TOS, $X
  pop $TOS
  $NEXT

$DEFCODE "-!", 2, 0, SUBSTORE
  ; ( amount address -- )
  pop $W
  lw $X, $TOS
  sub $X, $W
  stw $TOS, $X
  pop $TOS
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


;
; The last command - if it's not the last one, modify initial value of LATEST
;
$DEFCODE "BYE", 3, 0, BYE
  li r0, &bye_message
  call &writes

  call &halt

