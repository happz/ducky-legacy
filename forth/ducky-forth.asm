; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "forth/defs.asm"


.ifndef FORTH_TEXT_WRITABLE
  ; mprotect boundary pivots
  .section .text
text_boundary_first:
  ret

  .section .rodata
  .type rodata_boundary_first, int
  .int 0xDEAD
.endif


  ; Welcome and bye messages
  .section .rodata

.ifdef FORTH_WELCOME
  .type welcome_message, string
  .string "Ducky Forth welcomes you\n\r\n\r"
.endif

  .type bye_message, string
  .string "\r\nBye.\r\n"

  .text


halt:
  ; r0 - exit code
  int $INT_HALT


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


strcrc:
  ; r0: str addr, r1: str len
  push r1 ; original len
  push r2 ; saved str ptr
  push r3 ; current char
  mov r2, r0
  li r0, 0
.strcrc_loop:
  lb r3, r2
  add r0, r3
  inc r2
  dec r1
  bnz &.strcrc_loop
  pop r3
  pop r2
  pop r1
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
  outb $PORT_TTY_OUT, r2
  dec r1
  bnz &.__write_loop
  pop r2
.__write_quit:
  ret


writec:
  ; r0 - char
  outb $PORT_TTY_OUT, r0
  ret


writes:
  ; r0 - ptr
  push r1
.__writes_loop:
  lb r1, r0
  bz &.__writes_quit
  outb $PORT_TTY_OUT, r1
  inc r0
  j &.__writes_loop
.__writes_quit:
  pop r1
  ret


writeln:
  ; r0 - ptr
  ; r1 - size
  call &write
  j &write_new_line ; tail call


writesln:
  ; r0 - ptr
  call &writes
  j &write_new_line ; tail call


write_new_line:
  push r0
  li r0, 0xD
  outb $PORT_TTY_OUT, r0
  li r0, 0xA
  outb $PORT_TTY_OUT, r0
  pop r0
  ret


write_word_name:
  push r1
  push r2
  mov r1, r0
  mov r2, r0
  add r1, $wr_namelen
  lb r1, r1
  add r2, $wr_name
.__write_word_name_loop:
  lb r0, r2
  outb $PORT_TTY_OUT, r0
  inc r2
  dec r1
  bnz &.__write_word_name_loop
  call &write_new_line
  pop r2
  pop r1
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
  lb r1, r1
  call &write
  ; postfix + new line
  li r0, &buffer_print_postfix
  call &writesln
  pop r1
  pop r0
  ret


mm_area_remove_flag:
  ; r0 - start address
  ; r1 - end address
  ; r2 - segment
  ; r3 - flag to remove
  push r4
  push r5

  ; align addresses...
  $align_page r0
  $align_page r1
  ; and save them for later
  push r0
  push r1
  push r2
  push r3

  ; shift args and make space for operation argument
  mov r3, r2 ; segment -> r3
  mov r2, r1 ; end -> r2
  mov r1, r0 ; start -> r1
  li r0, $MM_OP_MTELL
  int $INT_MM

  cmp r0, 0
  bnz &halt

  ; save returned flags
  mov r4, r1

  pop r5 ; flag to remove
  pop r3 ; segment
  pop r2 ; end
  pop r1 ; start
  li r0, $MM_OP_MPROTECT
  ; add returned flags to segment
  or r3, r4
  ; and flags argument with all flags except the one we should remove
  not r5
  and r3, r5
  int $INT_MM

  cmp r0, 0
  bnz &halt

  pop r5
  pop r4
  ret


mm_area_add_flag:
  ; r0 - start address
  ; r1 - end address
  ; r2 - segment
  ; r3 - flag to add
  push r4
  push r5

  ; align addresses...
  $align_page r0
  $align_page r1
  ; and save them for later
  push r0
  push r1
  push r2
  push r3

  ; shift args and make space for operation argument
  mov r3, r2 ; segment -> r3
  mov r2, r1 ; end -> r2
  mov r1, r0 ; start -> r1
  li r0, $MM_OP_MTELL
  int $INT_MM

  cmp r0, 0
  bnz &halt

  ; save returned flags
  mov r4, r1

  pop r5 ; flag to add
  pop r3 ; segment
  pop r2 ; end
  pop r1 ; start
  li r0, $MM_OP_MPROTECT
  ; add returned flags to segment
  or r3, r4
  ; and add our flag
  or r3, r5
  int $INT_MM

  cmp r0, 0
  bnz &halt

  pop r5
  pop r4
  ret

mm_area_alloc:
  ; r0 - pages count
  push r1
  push r2

  mov r2, r0 ; save pages count
  ; call alloc
  mov r1, r0
  li r0, $MM_OP_ALLOC
  int $INT_MM

  cmp r0, 0xFFFF
  be &halt

  ; call mprotect
  push r0 ; save area address
  mul r2, $PAGE_SIZE
  add r2, r0
  mov r1, r2
  li r2, $MM_FLAG_DS
  li r3, $MM_FLAG_READ
  or r3, $MM_FLAG_WRITE
  call &mm_area_add_flag

  pop r0 ; pop area address
  pop r2
  pop r1
  ret


mm_area_free:
  ; r0 - address
  ; r1 - pages count
  push r2

  mov r2, r1
  mov r1, r0
  li r0, $MM_OP_FREE
  int $INT_MM

  cmp r0, 0
  bne &halt

  pop r2
  ret


init_crcs:
.ifndef FORTH_TEXT_WRITABLE
  li r0, $TEXT_OFFSET
  li r1, &text_boundary_last
  li r2, $MM_FLAG_CS
  li r3, $MM_FLAG_WRITE
  call &mm_area_add_flag

  li r0, &rodata_boundary_first
  li r1, &rodata_boundary_last
  li r2, $MM_FLAG_DS
  li r3, $MM_FLAG_WRITE
  call &mm_area_add_flag
.endif

  push r0 ; str ptr, crc
  push r1 ; str len
  push r2 ; link

  li r2, &var_LATEST

.__init_crcs_loop:
  lw r2, r2
  cmp r2, r2
  bz &.__init_crcs_quit

  mov r0, r2
  add r0, $wr_name

  mov r1, r2
  add r1, $wr_namelen
  lb r1, r1

  call &strcrc

  mov r1, r2
  add r1, $wr_namecrc
  stw r1, r0

  j &.__init_crcs_loop

.__init_crcs_quit:
  pop r2
  pop r1
  pop r0

.ifndef FORTH_TEXT_WRITABLE
  li r0, 0
  li r1, &text_boundary_last
  li r2, $MM_FLAG_CS
  li r3, $MM_FLAG_WRITE
  call &mm_area_remove_flag

  li r0, &rodata_boundary_first
  li r1, &rodata_boundary_last
  li r2, $MM_FLAG_DS
  li r3, $MM_FLAG_WRITE
  call &mm_area_remove_flag
.endif

  ret


main:
  li r0, 5
  outb 0x0300, r0

  ; init RSP
  li $RSP, &rstack_top

  ; save stack base
  li r0, &var_SZ
  stw r0, sp

  ; init words' crcs
  call &init_crcs

.ifdef FORTH_WELCOME
  ; print welcome message
  li r0, &welcome_message
  call &writes
.endif

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
  li r2, &input_buffer_address
  lw r2, r2
.__readline_loop:
  inb r3, $PORT_KEYBOARD_IN
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


input_stack_push:
  push r0 ; input_stack_ptr
  push r1 ; address
  push r2 ; value

  li r0, &input_stack_ptr
  lw r1, r0

  ; input buffer address
  li r2, &input_buffer_address
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; input buffer index
  li r2, &input_buffer_index
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; input buffer length
  li r2, &input_buffer_length
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; state
  li r2, &var_STATE
  lw r2, r2
  stw r1, r2
  add r1, $CELL

  stw r0, r1

  pop r2
  pop r1
  pop r0

  ret

input_stack_pop:
  push r0
  push r1
  push r2
  push r3

  li r0, &input_stack_ptr
  lw r1, r0

  ; state
  sub r1, $CELL
  li r2, &var_STATE
  lw r3, r1
  stw r2, r3
  ; input buffer length
  sub r1, $CELL
  li r2, &input_buffer_length
  lw r3, r1
  stw r2, r3
  ; input buffer index
  sub r1, $CELL
  li r2, &input_buffer_index
  lw r3, r1
  stw r2, r3
  ; input buffer address
  sub r1, $CELL
  li r2, &input_buffer_address
  lw r3, r1
  stw r2, r3

  stw r0, r1

  pop r3
  pop r2
  pop r1
  pop r0

  ret


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

  .type __unused__, byte
  .byte 0

  .type word_buffer_length, byte
  .byte 0

  .type word_buffer, space
  .space $WORD_SIZE

  .type input_buffer, space
  .space $INPUT_BUFFER_SIZE

  .type input_buffer_length, int
  .int 0

  .type input_buffer_index, int
  .int 0

  .type input_buffer_address, int
  .int &input_buffer

  ; when EVALUATE is called, current input source specification
  ; is saved on top of this stack
  .type input_stack, space
  .space $INPUT_STACK_SIZE

  ; the first free position in input_stack
  .type input_stack_ptr, int
  .int &input_stack

  ; if not zero, restore input source specification from stack
  .type input_stack_restorable, int
  .int 0

  .type rstack, space
  .space $RSTACK_SIZE

  .type rstack_top, int
  .int 0xFFFF

  ; User data area
  ; Keep it in separate section to keep it aligned, clean, unpoluted
  .section .userspace, rwblg
  .space $USERSPACE_SIZE


  .set link, 0

;
; Variables
;
$DEFVAR "UP", 2, 0, UP, $USERSPACE_BASE
$DEFVAR "STATE", 5, 0, STATE, 0
$DEFVAR "DP", 2, 0, DP, $USERSPACE_BASE
$DEFVAR "LATEST", 6, 0, LATEST, &name_BYE
$DEFVAR "S0", 2, 0, SZ, 0
$DEFVAR "BASE", 4, 0, BASE, 10


;
; Kernel words
;

$DEFCODE "VMDEBUGON", 9, 0, VMDEBUGON
  ; ( -- )
  li r0, $VMDEBUG_LOGGER_VERBOSITY
  li r1, $VMDEBUG_VERBOSITY_DEBUG
  int $INT_VMDEBUG
  $NEXT

$DEFCODE "VMDEBUGOFF", 10, 0, VMDEBUGOFF
  ; ( -- )
  li r0, $VMDEBUG_LOGGER_VERBOSITY
  li r1, $VMDEBUG_VERBOSITY_INFO
  int $INT_VMDEBUG
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
  $unpack_word_for_find
  call &.__FIND
  cmp r0, r0
  bz &.__INTERPRET_as_lit
  pop r1
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
  $unpack_word_for_find
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
  li r0, &input_buffer_address
  lw r0, r0
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

.ifdef FORTH_DEBUG_FIND
  .type find_debug_header, string
  .string "FIND WORD:\r\n"
.endif

$DEFCODE "EVALUATE", 8, 0, EVALUATE
  pop r1 ; length
  pop r0 ; address
  call &.__EVALUATE
  $NEXT

.__EVALUATE:
  ; save current input state
  call &input_stack_push
  push r2
  ; load new input buffer address
  li r2, &input_buffer_address
  stw r2, r0
  ; load new input buffer length
  li r2, &input_buffer_length
  stw r2, r1
  li r0, 0
  ; reset input buffer index
  li r2, &input_buffer_index
  stw r2, r0
  ; set STATE to "interpret"
  ;li r2, &var_STATE
  ;stw r2, r0
  pop r2
  ret


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
  li r3, &input_buffer_index
.__KEY_start_again:
  lw r2, r1
  lw r4, r3
  cmp r2, r4
  be &.__KEY_read_line
.__KEY_read_char:
  ; get char ptr
  li r5, &input_buffer_address
  lw r5, r5
  add r5, r4
  ; read char
  lb r0, r5
  ; and update vars
  inc r4
  stw r3, r4
.__KEY_ret:
  pop r5
  pop r4
  pop r3
  pop r2
  pop r1
  ret
.__KEY_read_line:
  li r2, &input_stack_ptr
  lw r2, r2
  li r4, &input_stack
  cmp r2, r4
  be &.__KEY_do_read_line
  call &input_stack_pop
  li r0, 0x0A
  j &.__KEY_ret
.__KEY_do_read_line:
  call &readline
  j &.__KEY_start_again


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
  pop r0
  call &.__EMIT
  $NEXT

.__EMIT:
  outb $PORT_TTY_OUT, r0
  ret


$DEFCODE "TYPE", 4, 0, TYPE
  ; ( address length -- )
  pop r1
  pop r0
  call &write
  $NEXT


$DEFCODE "WORD", 4, 0, WORD
  ; ( -- c-addr )
  call &.__WORD
  push r0
  $NEXT

.__WORD:
  call &.__KEY
  ; if key's lower or eaqual to space, it's considered as a white space, and ignored.
  ; this removes leading white space
  cmp r0, 0x20
  ble &.__WORD
  push r1
  li r1, &word_buffer
.__WORD_store_char:
  stb r1, r0
  inc r1
  call &.__KEY
  cmp r0, 0x20 ; space
  bg &.__WORD_store_char
  sub r1, &word_buffer
  li r0, &word_buffer_length
  stb r0, r1
  pop r1
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
  li $W, &input_buffer_address
  lw $W, $W
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
  inc r0
  j &.__NUMBER_quit


$DEFCODE "FIND", 4, 0, FIND
  ; ( c-addr -- 0 0 | xt 1 | xt -1 )
  pop r1
  mov r0, r1
  inc r0
  lb r1, r1
  call &.__FIND
  cmp r0, 0
  bz &.__FIND_notfound
  push r1
  call &.__TCFA
  pop r1
  push r0
  push r1
  j &.__FIND_next
.__FIND_notfound:
  push 0
  push 0
.__FIND_next:
  $NEXT


.__FIND:
.ifdef FORTH_DEBUG_FIND
  push r0
  li r0, &find_debug_header
  call &writesln
  pop r0
  call &write_word_buffer
.endif

  ; r0 - address
  ; r1 - length
  ; save working registers
  push r2 ; word ptr
  push r3 ; crc

  li r2, &var_LATEST
  lw r2, r2

  push r0
  call &strcrc
  mov r3, r0
  pop r0

.__FIND_loop:
  cmp r2, r2
  bz &.__FIND_fail

.ifdef FORTH_DEBUG_FIND
  ; print name
  push r0
  mov r0, r2
  call &write_word_name
  pop r0
.endif

  ; check HIDDEN flag
  push r2
  add r2, $wr_flags
  lb r2, r2
  and r2, $F_HIDDEN
  bz &.__FIND_hidden_success
  pop r2
  lw r2, r2
  j &.__FIND_loop

.__FIND_hidden_success:
  pop r2

  ; check crc
  push r2
  add r2, $wr_namecrc
  lw r2, r2
  cmp r2, r3
  be &.__FIND_crc_success
  pop r2
  lw r2, r2 ; load link content
  j &.__FIND_loop

.__FIND_crc_success:
  pop r2

.__FIND_strcmp:
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
  add r2, $wr_flags
  lb r2, r2
  and r2, $F_IMMED
  bnz &.__FIND_immed
  li r1, 0xFFFF
  j &.__FIND_finish
.__FIND_immed:
  li r1, 1
.__FIND_finish:
  pop r3
  pop r2
  ret
.__FIND_fail:
  pop r3
  pop r2
  li r0, 0
  li r1, 0
  ret


$DEFCODE "'", 1, $F_IMMED, TICK
  call &.__WORD
  $unpack_word_for_find
  call &.__FIND
  call &.__TCFA
  push r0
  $NEXT


$DEFCODE "[']", 3, 0, BRACKET_TICK
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


$DEFCODE "EXECUTE", 7, 0, EXECUTE
  pop $W
  lw $X, $W
  j $X


$DEFCODE "LIT", 3, 0, LIT
  lw $W, $FIP
  push $W
  add $FIP, $CELL
  $NEXT


$DEFCODE "HEADER,", 7, 0, HEADER_COMMA
  ; ( c-addr -- )
  pop r1
  mov r0, r1
  inc r0
  lb r1, r1
  call &.__HEADER_COMMA
  $NEXT

.__HEADER_COMMA:
  ; r0: str ptr, r1: str len
  ; save working registers
  push r2 ; DP address
  push r3 ; DP value
  push r4 ; LATEST address
  push r5 ; LATEST value
  push r6 ; flags/length
  push r7 ; current word char
  ; init registers
  li r2, &var_DP
  lw r3, r2
  li r4, &var_LATEST
  lw r5, r4
  ; align DP, I want words aligned
  $align2 r3
  ; store LATEST as a link value of new word
  stw r3, r5
  mov r5, r3
  stw r4, r5
  ; and move DP to next cell
  add r3, 2
  ; save name crc
  push r0
  push r1
  call &strcrc
  stw r3, r0
  pop r1
  pop r0
  ; and move DP to next cell
  add r3, 2
  ; save flags
  li r6, 0
  stb r3, r6
  inc r3
  ; save unaligned length ...
  stb r3, r1
  inc r3
  ; but shift DP to next aligned address
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
  ; align DP - this will "add" padding byte to name automagicaly
  $align2 r3
  ; save vars
  stw r2, r3 ; DP
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
  push r1 ; DP address
  push r2 ; DP value
  li r1, &var_DP
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
  .int &DROP
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


$DEFCODE "MOD", 3, 0, MOD
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
  inc r0
  lb $W, r0 ; load the first character of next word into W...
  push $W
  $NEXT


$DEFCODE "[CHAR]", 6, $F_IMMED, BRACKETCHAR
  call &.__WORD
  inc r0
  lb $W, r0
  li r0, &LIT
  call &.__COMMA
  mov r0, $W
  call &.__COMMA
  $NEXT


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

$DEFCODE "SQUOTE_LITSTRING", 9, 0, SQUOTE_LITSTRING
  ; ( -- c-addr u )
  lb $W, $FIP     ; load length
  inc $FIP        ; FIP points to string
  push $FIP       ; push string addr
  push $W         ; push string length
  add $FIP, $W    ; skip string
  $align2 $FIP    ; align FIP
  $NEXT

$DEFCODE "CQUOTE_LITSTRING", 9, 0, CQUOTE_LITSTRING
  ; ( -- c-addr )
  push $FIP       ; push c-addr
  lb $W, $FIP     ; load string length
  inc $FIP        ; skip length
  add $FIP, $W    ; skip string
  $align2 $FIP    ; align FIP
  $NEXT


$DEFCODE "TELL", 4, 0, TELL
  ; ( c-addr u -- )
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


$DEFCODE "(+LOOP)", 7, 0, PAREN_PLUSLOOP
  $poprsp $W ; index
  $poprsp $X ; control
  pop $Y     ; increment N
  bs &.__PAREN_PLUSLOOP_dec
  add $W, $Y
  cmp $W, $X
  bg &.__PAREN_PLUSLOOP_next
  j &.__PAREN_PLUSLOOP_iter
.__PAREN_PLUSLOOP_dec:
  add $W, $Y
  cmp $W, $X
  bl &.__PAREN_PLUSLOOP_next
.__PAREN_PLUSLOOP_iter:
  $pushrsp $X
  $pushrsp $W
  lw $W, $FIP
  add $FIP, $W
  $NEXT
.__PAREN_PLUSLOOP_next:
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


$DEFCODE "\\\\", 1, $F_IMMED, BACKSLASH
  li $W, &input_buffer_length
  lw $W, $W
  li $X, &input_buffer_index
  stw $X, $W
  $NEXT

$DEFCODE "HERE", 4, 0, HERE
  li $W, &var_DP
  lw $W, $W
  push $W
  $NEXT


;
; The last command - if it's not the last one, modify initial value of LATEST
;
$DEFCODE "BYE", 3, 0, BYE
  li r0, &bye_message
  call &writes

  li r0, 0
  call &halt


.ifndef FORTH_TEXT_WRITABLE
  ; mprotect boundary pivots
  .section .rodata
  .type rodata_boundary_last, int
  .int 0xDEAD

  .section .text
text_boundary_last:
  ret
.endif
