; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "ducky-forth-defs.asm"
.include "control.asm"
.include "keyboard.asm"
.include "rtc.asm"
.include "boot.asm"
.include "tty.asm"


  .text

  ; This is where bootloader jump to, main entry point
_entry:
  $boot_progress
  j &boot_phase1


__vmdebug_on:
  push r0
  push r1
  li r0, 0x00
  li r1, 0x00
  int 18
  pop r1
  pop r0
  ret

__vmdebug_off:
  push r0
  push r1
  li r0, 0x00
  li r1, 0x01
  int 18
  pop r1
  pop r0
  ret

  .section .rodata

  .type rodata_boundary_first, int
  .int 0xDEADBEEF


  ; Welcome and bye messages
  .section .rodata

.ifdef FORTH_WELCOME
  .type welcome_message, string
  .string "Ducky Forth welcomes you\n\r\n\r"
.endif

  .type bye_message, string
  .string "\r\nBye.\r\n"

  .text


;
; void halt(u32_t exit_code)
;
halt:
  hlt r0


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
; void memcpy4(void *src, void *dst, u32_t length)
;
; Copy content of memory at SRC, of length of LENGTH bytes, to address DST.
; Length of area must be multiply of 4. Source and destination areas should
; not overlap, otherwise memcpy could lead to unpredicted results.
;
memcpy4:
  cmp r2, 0
  bz &__memcpy4_quit
  push r3
__memcpy4_loop:
  lw r3, r0
  stw r1, r3
  add r0, 4
  add r1, 4
  sub r2, 4
  bnz &__memcpy4_loop
  pop r3
__memcpy4_quit:
  ret


;
; u32_t strcmp(char *s1, u32_t s1_length, char *s2, u32_t s2_length)
;
; Returns 0 if string are equal, 1 otherwise
;
strcmp:
  cmp r1, r3
  bne &__strcmp_neq
  bz &__strcmp_eq
  ; save working registers
  push r4 ; curr s1 char
  push r5 ; curr s2 char
__strcmp_loop:
  lb r4, r0
  lb r5, r2
  inc r0
  inc r2
  cmp r4, r5
  be &__strcmp_next
  pop r5
  pop r4
__strcmp_neq:
  li r0, 1
  ret
__strcmp_next:
  dec r1
  bnz &__strcmp_loop
  pop r5
  pop r4
__strcmp_eq:
  li r0, 0
  ret


;
; u32_t strcrc(char *s, u32_t len)
;
strcrc:
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


;
; void write(char *s, u32_t len)
;
; Write string S of length LEN to standard terminal output.
;
write:
  cmp r1, r1
  bz &__write_quit
  push r2
__write_loop:
  lb r2, r0
  inc r0
  outb $TTY_PORT_DATA, r2
  dec r1
  bnz &__write_loop
  pop r2
__write_quit:
  ret


;
; void writec(u8_t c)
;
; Write character C to standard terminal output.
;
writec:
  outb $TTY_PORT_DATA, r0
  ret


;
; void writes(char *s)
;
; Write null-terminated string S to standard terminal output.
;
writes:
  push r1
__writes_loop:
  lb r1, r0
  bz &__writes_quit
  outb $TTY_PORT_DATA, r1
  inc r0
  j &__writes_loop
__writes_quit:
  pop r1
  ret


;
; void writeln(char *s, u32_t len)
;
; Write string S of length LEN to standard terminal output, and move cursor to a new line.
;
writeln:
  call &write
  j &write_new_line ; tail call


;
; void writesln(char *s)
;
; Write null-terminated string S to standard terminal output, and move cursor to a new line.
;
writesln:
  call &writes
  j &write_new_line ; tail call


;
; void write_new_line(void)
;
; Emit control characters to force new line (\r\n).
;
write_new_line:
  push r0
  li r0, 0xD
  outb $TTY_PORT_DATA, r0
  li r0, 0xA
  outb $TTY_PORT_DATA, r0
  pop r0
  ret


;
; void write_word_name(void *ptr)
;
; Write name of word, pointed to by PTR, to standard terminal output, and move cursor to new line.
;
write_word_name:
  push r1
  push r2
  mov r1, r0
  mov r2, r0
  add r1, $wr_namelen
  lb r1, r1
  add r2, $wr_name
__write_word_name_loop:
  lb r0, r2
  outb $TTY_PORT_DATA, r0
  inc r2
  dec r1
  bnz &__write_word_name_loop
  call &write_new_line
  pop r2
  pop r1
  ret


;
; void write_word_buffer(void)
;
; Write content of internal word buffer to standard terminal output, surrounded
; by pre- and post-fix for better readability.
;
write_word_buffer:
  push r0
  push r1
  ; prefix
  la r0, &buffer_print_prefix
  call &writes
  ; word buffer
  la r0, &word_buffer
  la r1, &word_buffer_length
  lb r1, r1
  call &write
  ; postfix + new line
  la r0, &buffer_print_postfix
  call &writesln
  pop r1
  pop r0
  ret


;
; void init_crcs(void)
;
; Compute name CRC for each exisitng word.
;
init_crcs:
  ; Since, by default, we're still in privileged mode, it's not
  ; necessarry to disable read-only protection of .text and .rodata.
  ; There's also no PT anyway...

  la r2, &var_LATEST

__init_crcs_loop:
  lw r2, r2
  cmp r2, r2
  bz &__init_crcs_quit

  mov r0, r2
  add r0, $wr_name

  mov r1, r2
  add r1, $wr_namelen
  lb r1, r1

  call &strcrc

  mov r1, r2
  add r1, $wr_namecrc
  sts r1, r0

  j &__init_crcs_loop

__init_crcs_quit:
  ; Flush data and PTE caches
  ; It is possible to flush data cache *after* enabling
  ; read-only access because we're still in privileged mode,
  ; but if this changes, it would cause an access violation.
  fptc

  ret


;
; void __relocate_section(u32_t *first, u32_t *last)
;
__relocate_section:
  ; we're moving section to the beggining of the address space,
  ; basically subtracting BOOT_LOADER_ADDRESS from its start
  li r10, $BOOT_LOADER_ADDRESS
  mov r2, r1

  ; construct arguments for memcpy4
  ; src: first, no change necessary
  ; length: last - first
  sub r2, r0

  ; dst: start - BOOT_LOADER_ADDRESS
  mov r1, r0
  sub r1, r10

  call &memcpy4

  ret


;
; void __relocate_sections(void)
;
; FORTH image is loaded by bootloader to address BOOT_LOADER_ADDRESS. This is
; unfortunate because - thanks to way how threaded code is implemented here -
; this offset breaks all absolute, compile-time references, hardcoded into
; links between words. Most of the other code would not care about running
; with a different base address but this breaks. I can't find other way how
; to deal with this, therefore the first think kernel does is relocating
; itself to the beggining of the address space.
;
; Unfortunatelly, there are some obstackles in the way - IVT, HDT, CWT, maybe
; even some mmaped IO ports, ... IVT and HDT can be moved, devices can be
; convinced to move ports to differet offsets, but CWT is bad - if we want to
; use more than one CPU core... Which we don't want to \o/
__relocate_sections:
  li r0, $BOOT_LOADER_ADDRESS
  la r1, &text_boundary_last
  call &__relocate_section
  $boot_progress

  la r0, &rodata_boundary_first
  la r1, &rodata_boundary_last
  call &__relocate_section
  $boot_progress

  la r0, &data_boundary_first
  la r1, &data_boundary_last
  call &__relocate_section
  $boot_progress

  li r0, $USERSPACE_BASE
  li r1, $BOOT_LOADER_ADDRESS
  add r0, r1
  mov r1, r0
  add r1, $USERSPACE_SIZE
  call &__relocate_section
  $boot_progress

  ret


;
; void boot_phase1(void) __attribute__((noreturn))
;
; This is the first phae of kernel booting process. Its main goal is to
; relocate kernel sections to the beggining of the address space.
;
; Until the stack is initialized, and because of the nature of things,
; it's not necessary to honor callee-saved registers in routines.
;
boot_phase1:
  call &__vmdebug_off

  ; relocate image to more convenient place
  call &__relocate_sections

  $boot_progress

  ; now do long jump to new, relocated version of boot_phase2
  la r0, &boot_phase2
  li r1, $BOOT_LOADER_ADDRESS
  sub r0, r1
  j r0


;
; void boot_phase2(void) __attribute__((noreturn))
;
; This is the second phase of kernel booting process. It does the rest of
; necessary work before handing over to FORTH words.
;
boot_phase2:
  ; set RTC frequency
  li r0, $RTC_FREQ
  outb $RTC_PORT_FREQ, r0

  ; init stack - the next-to-last page is our new stack
  li sp, 0xFF00
  liu sp, 0xFFFF
  la r0, &var_SZ
  stw r0, sp

  ; init return stack - the next-to-next-to-last page is our new return stack
  li $RSP, 0xFE00
  liu $RSP, 0xFFFF

  ; IVT - use the last page
  li r0, 0xFF00
  liu r0, 0xFFFF
  ctw $CONTROL_IVT, r0

  ; init all entries to fail-safe
  la r1, &failsafe_isr
  li r2, 0xFD00
  liu r2, 0xFFFF

  mov r3, r0
  mov r4, r0
  add r4, $PAGE_SIZE
__boot_phase2_ivt_failsafe_loop:
  stw r3, r1
  add r3, 0x04
  stw r3, r2
  add r3, 0x04
  cmp r3, r4
  bne &__boot_phase2_ivt_failsafe_loop

  ; set the first entry to RTC ISR
  la r1, &rtc_isr
  li r2, 0xFC00
  liu r2, 0xFFFF
  stw r0, r1
  add r0, 0x04
  stw r0, r2
  add r0, 0x04

  ; set the second entry to NOP ISR for keyboard
  la r1, &nop_isr
  li r2, 0xFB00
  liu r2, 0xFFFF
  stw r0, r1
  add r0, 0x04
  stw r0, r2
  add r0, 0x04

.ifdef FORTH_DEBUG
  ; init log stack
  li $LSP, 0xFA00
  liu $LSP, 0xFFFF
.endif

  ; init LATEST
  la r0, &var_LATEST
  la r1, &name_BYE
  stw r0, r1

  ; init words' crcs
  call &init_crcs

  ; give up the privileged mode
  ; lpm
  sti

.ifdef FORTH_WELCOME
  ; print welcome message
  la r0, &welcome_message
  call &writes
.endif

  ; and boot the FORTH itself...
  la $FIP, &cold_start
  $NEXT


;
; void failsafe_isr(void) __attribute__((noreturn))
;
; Fail-safe interrupt service routine - if this interrupt
; gets triggered, kill kernel.
;
failsafe_isr:
  hlt 0x2000


;
; void nop_isr(void) __attribute__((noreturn))
;
; NOP ISR - just retint, we have nothing else to do.
;
nop_isr:
  retint


;
; void rtc_isr(void) __attribute__((noreturn))
;
; RTC interrupt service routine.
;
rtc_isr:
  retint


;
; void readline(void)
;
; Read characters from keyboard, store them in input buffer. When \n or \r are
; encountered, return back to caller, signalising new lien is ready in buffer.
; Input buffer index variables are set properly.
;
readline:
  push r0 ; &input_buffer_length
  push r1 ; input_buffer_length
  push r2 ; input_buffer
  push r3 ; current input char
  ; now init variables
  la r0, &input_buffer_length
  li r1, 0 ; clear input buffer
  la r2, &input_buffer_address
  lw r2, r2
__readline_loop:
  inb r3, $KBD_PORT_DATA
  cmp r3, 0xFF
  be &__readline_wait_for_input
  stb r2, r3
  inc r1
  inc r2
  cmp r3, 0x0A ; nl
  be &__readline_quit
  cmp r3, 0x0D ; cr
  be &__readline_quit
  j &__readline_loop
__readline_quit:
  stw r0, r1 ; save input_buffer_length
  ; reset input_buffer_index
  la r0, &input_buffer_index
  li r1, 0
  stw r0, r1
  pop r3
  pop r2
  pop r1
  pop r0
  ret
__readline_wait_for_input:
  ; This is a small race condition... What if new key
  ; arrives after inb and before idle? We would be stuck until
  ; the next key arrives (and it'd be Enter, nervously pressed
  ; by programmer while watching machine "doing nothing"
  idle
  j &__readline_loop


input_stack_push:
  push r0 ; input_stack_ptr
  push r1 ; address
  push r2 ; value

  la r0, &input_stack_ptr
  lw r1, r0

  ; input buffer address
  la r2, &input_buffer_address
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; input buffer index
  la r2, &input_buffer_index
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; input buffer length
  la r2, &input_buffer_length
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; state
  la r2, &var_STATE
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

  la r0, &input_stack_ptr
  lw r1, r0

  ; state
  sub r1, $CELL
  la r2, &var_STATE
  lw r3, r1
  stw r2, r3
  ; input buffer length
  sub r1, $CELL
  la r2, &input_buffer_length
  lw r3, r1
  stw r2, r3
  ; input buffer index
  sub r1, $CELL
  la r2, &input_buffer_index
  lw r3, r1
  stw r2, r3
  ; input buffer address
  sub r1, $CELL
  la r2, &input_buffer_address
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
  bz &__DODOES_push

  $pushrsp $FIP
  mov $FIP, $W

__DODOES_push:
  add $W, $CELL           ; W points to Param Field #1 - payload address
  push $W
  $NEXT


  .section .rodata
  .align 4
cold_start:
  ;.int &BYE
  .int &QUIT


  .section .data

  .align 4
  .type data_boundary_first, int
  .int 0xDEADBEEF

  .type word_buffer_length, byte
  .byte 0

  ; word_buffer lies right next to word_buffer_length, pretending it's
  ; a standard counted string <length><chars...>
  .type word_buffer, space
  .space $WORD_BUFFER_SIZE

  .align 4
  .type input_buffer, space
  .space $INPUT_BUFFER_SIZE

  .align 4
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
  .align 4
  .type input_stack_ptr, int
  .int &input_stack

  ; if not zero, restore input source specification from stack
  .type input_stack_restorable, int
  .int 0

  .type rstack_top, int
  .int 0xFFFFFE00

  .type jiffies, int
  .int 0x00000000

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


$DEFCODE "VMDEBUGON", 9, $F_IMMED, VMDEBUGON
  call &__vmdebug_on
  $NEXT

$DEFCODE "VMDEBUGOFF", 10, $F_IMMED, VMDEBUGOFF
  call &__vmdebug_off
  $NEXT


;
; Kernel words
;

$DEFCODE "INTERPRET", 9, 0, INTERPRET
  li r0, 0x20 ; space as delimiter
  call &__WORD

  push r6
  push r5
  la r5, &var_STATE
  lw r5, r5
  li r6, 0 ; interpret_as_lit?

  ; search dictionary
  push r0
  push r1
  $unpack_word_for_find
  call &__FIND
  cmp r0, r0
  bz &__INTERPRET_as_lit
  pop r1
  pop r6 ; pop r0
  li r6, 0 ; restore interpret_as_lit
  mov r1, r0
  add r1, $wr_flags
  call &__TCFA
  lb r1, r1
  and r1, $F_IMMED
  cmp r1, r1
  bnz &__INTERPRET_execute
  j &__INTERPRET_state_check

__INTERPRET_as_lit:
  pop r1
  pop r0
  inc r6
  $unpack_word_for_find
  call &__NUMBER
  ; r0 - number, r1 - unparsed chars
  cmp r1, r1
  bnz &__INTERPRET_parse_error
  mov r1, r0  ; save number
  la r0, &LIT ; and replace with LIT

__INTERPRET_state_check:
  cmp r5, r5
  bz &__INTERPRET_execute
  call &__COMMA ; append r0 (aka word) to current definition
  cmp r6, r6
  bz &__INTERPRET_next ; if not LIT, just leave
  mov r0, r1
  call &__COMMA ; append r0 (aka number) to current definition
  j &__INTERPRET_next

__INTERPRET_execute:
  cmp r6, r6
  bnz &__INTERPRET_execute_lit
  pop r5
  pop r6
  mov $W, r0
  lw $X, r0
  $log_word $W
  $log_word $X
  j $X

__INTERPRET_execute_lit:
  pop r5
  pop r6
  push r1
  $NEXT

__INTERPRET_parse_error:
  ; error message
  la r0, &parse_error_msg
  call &writes
  ; input buffer label
  la r0, &parse_error_input_buffer_prefix
  call &writes
  ; prefix
  la r0, &buffer_print_prefix
  call &writes
  ; input buffer
  la r0, &input_buffer_address
  lw r0, r0
  la r1, &input_buffer_length
  lw r1, r1
  call &write
  ; new line
  li r0, 0
  li r1, 0
  call &writeln
  ; word buffer label
  la r0, &parse_error_word_buffer_prefix
  call &writes
  call &write_word_buffer
  call &halt

__INTERPRET_next:
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
  call &__EVALUATE
  $NEXT

__EVALUATE:
  ; save current input state
  call &input_stack_push
  push r2
  ; load new input buffer address
  la r2, &input_buffer_address
  stw r2, r0
  ; load new input buffer length
  la r2, &input_buffer_length
  stw r2, r1
  li r0, 0
  ; reset input buffer index
  la r2, &input_buffer_index
  stw r2, r0
  ; set STATE to "interpret"
  ;la r2, &var_STATE
  ;stw r2, r0
  pop r2
  ret


$DEFCODE ">IN", 3, 0, TOIN
  la $W, &input_buffer_index
  push $W
  $NEXT


$DEFCODE "KEY", 3, 0, KEY
  ; ( -- n )
  call &__KEY
  push r0
  $NEXT

__KEY:
  ; r0 - input char
  push r1 ; &input_buffer_length
  push r2 ; input_buffer_length
  push r3 ; &input_buffer_index
  push r4 ; input_buffer_index
  push r5 ; index_buffer ptr
  la r1, &input_buffer_length
  la r3, &input_buffer_index
__KEY_start_again:
  lw r2, r1
  lw r4, r3
  cmp r2, r4
  be &__KEY_read_line
__KEY_read_char:
  ; get char ptr
  la r5, &input_buffer_address
  lw r5, r5
  add r5, r4
  ; read char
  lb r0, r5
  ; and update vars
  inc r4
  stw r3, r4
__KEY_ret:
  pop r5
  pop r4
  pop r3
  pop r2
  pop r1
  ret
__KEY_read_line:
  la r2, &input_stack_ptr
  lw r2, r2
  la r4, &input_stack
  cmp r2, r4
  be &__KEY_do_read_line
  call &input_stack_pop
  li r0, 0x0A
  j &__KEY_ret
__KEY_do_read_line:
  call &readline
  j &__KEY_start_again


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
  pop r0
  call &__EMIT
  $NEXT

__EMIT:
  outb $TTY_PORT_DATA, r0
  ret


$DEFCODE "TYPE", 4, 0, TYPE
  ; ( address length -- )
  pop r1
  pop r0
  call &write
  $NEXT


$DEFCODE "WORD", 4, 0, WORD
  ; ( char "<chars>ccc<char>" -- c-addr )
  pop r0
  call &__WORD
  push r0
  $NEXT

$DEFCODE "DWORD", 5, 0, DWORD
  ; ( "<chars>ccc<char>" -- c-addr )
  ; like WORD but with space as a delimiter ("default WORD")
  call &__DWORD
  push r0
  $NEXT


__WORD:
  ; delimiter -- c-addr

  push r1
  push r2
  push r3
  mov r3, r0 ; save delimiter

__WORD_key:
  ; first, skip leading delimiters
  call &__KEY
  cmp r0, r3
  be &__WORD_key
  ; also, skip leading white space - except the space itself...
  cmp r0, 0x20
  bl &__WORD_key

  la r1, &word_buffer
__WORD_store_char:
  stb r1, r0
  inc r1
  call &__KEY
  cmp r0, r3 ; compare with delimiter
  be &__WORD_save
  cmp r0, 0x20
  bl &__WORD_save
  j &__WORD_store_char
__WORD_save:
  la r2, &word_buffer
  sub r1, r2
  la r0, &word_buffer_length
  stb r0, r1
  pop r3
  pop r2
  pop r1
  ; call &write_word_buffer
  ret

__DWORD:
  li r0, 0x20
  j &__WORD


$DEFCODE "SOURCE", 6, 0, SOURCE
  ; ( address length )
  la $W, &input_buffer_address
  lw $W, $W
  push $W
  la $W, &input_buffer_length
  lw $W, $W
  push $W
  $NEXT


$DEFCODE "NUMBER", 6, 0, NUMBER
  ; ( address length -- number unparsed_chars )
  pop r1
  pop r0
  call &__NUMBER
  push r0
  push r1
  $NEXT


__NUMBER:
  cmp r1, r1
  bz &__NUMBER_quit_noclean
  ; save working registers
  push r2 ; BASE
  push r3 ; char ptr
  push r4 ; current char
  ; set up working registers
  la r2, &var_BASE
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
  bne &__NUMBER_convert_digit
  pop r4 ; it's minus, no need to preserve r4, so pop 0 from stack...
  push 1 ; ... and push 1 to indicate negative number
  ; if there are no remaining chars, we got only '-' - that's bad, quit
  cmp r1, r1
  bnz &__NUMBER_loop
  pop r1 ; 1 was on stack to signal negative number, reuse it as error message
__NUMBER_quit:
  pop r4
  pop r3
  pop r2
__NUMBER_quit_noclean:
  ret

__NUMBER_loop:
  cmp r1, r1
  bz &__NUMBER_negate

  lb r4, r3
  inc r3
  dec r1

__NUMBER_convert_digit:
  ; if char is lower than '0' then it's bad - quit
  sub r4, 0x30
  bs &__NUMBER_fail
  ; if char is lower than 10, it's a digit, convert it according to base
  cmp r4, 10
  bl &__NUMBER_check_base
  ; if it's outside the alphabet, it's bad - quit
  sub r4, 17 ; 'A' - '0' = 17
  bs &__NUMBER_fail
  add r4, 10

__NUMBER_check_base:
  ; if digit is bigger than base, it's bad - quit
  cmp r4, r2
  bge &__NUMBER_fail

  mul r0, r2
  add r0, r4
  j &__NUMBER_loop

__NUMBER_fail:
  li r1, 1

__NUMBER_negate:
  pop r2 ; BASE no longer needed, use its register
  cmp r2, r2
  bz &__NUMBER_quit
  not r0
  inc r0
  j &__NUMBER_quit


$DEFCODE "FIND", 4, 0, FIND
  ; ( c-addr -- 0 0 | xt 1 | xt -1 )
  pop r1
  mov r0, r1
  inc r0
  lb r1, r1
  call &__FIND
  cmp r0, 0
  bz &__FIND_notfound
  push r1
  call &__TCFA
  pop r1
  push r0
  push r1
  j &__FIND_next
__FIND_notfound:
  push 0
  push 0
__FIND_next:
  $NEXT


__FIND:
.ifdef FORTH_DEBUG_FIND
  push r0
  la r0, &find_debug_header
  call &writesln
  pop r0
  call &write_word_buffer
.endif

  ; r0 - address
  ; r1 - length
  ; save working registers
  push r2 ; word ptr
  push r3 ; crc

  la r2, &var_LATEST
  lw r2, r2

  push r0
  call &strcrc
  mov r3, r0
  pop r0

__FIND_loop:
  cmp r2, r2
  bz &__FIND_fail

.ifdef FORTH_DEBUG_FIND
  ; print name
  ;push r0
  ;mov r0, r2
  ;call &write_word_name
  ;pop r0
.endif

  ; check HIDDEN flag
  push r2
  add r2, $wr_flags
  lb r2, r2
  and r2, $F_HIDDEN
  bz &__FIND_hidden_success
  pop r2
  lw r2, r2
  j &__FIND_loop

__FIND_hidden_success:
  pop r2

  ; check crc
  push r2
  add r2, $wr_namecrc
  ls r2, r2
  cmp r2, r3
  be &__FIND_crc_success
  pop r2
  lw r2, r2 ; load link content
  j &__FIND_loop

__FIND_crc_success:
  pop r2

__FIND_strcmp:
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
  be &__FIND_success
  pop r3
  pop r2
  pop r1
  pop r0
  lw r2, r2 ; load link content
  j &__FIND_loop
__FIND_success:
  pop r3 ; this one we used just for calling strcmp
  pop r2
  pop r1
  pop r0
  mov r0, r2
  add r2, $wr_flags
  lb r2, r2
  and r2, $F_IMMED
  bnz &__FIND_immed
  $load_minus_one r1
  j &__FIND_finish
__FIND_immed:
  li r1, 1
__FIND_finish:
  pop r3
  pop r2
  ret
__FIND_fail:
  pop r3
  pop r2
  li r0, 0
  li r1, 0
  ret


$DEFCODE "'", 1, $F_IMMED, TICK
  call &__DWORD
  $unpack_word_for_find
  call &__FIND
  call &__TCFA
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
  call &__TCFA
  push r0
  $NEXT

__TCFA:
  add r0, $wr_namelen
  push r1
  lb r1, r0
  inc r0
  add r0, r1
  $align4 r0
  pop r1
  ret


$DEFWORD ">DFA", 4, 0, TDFA
  .int &TCFA
  .int &INCR2
  .int &EXIT


$DEFCODE "EXECUTE", 7, 0, EXECUTE
  pop $W
  lw $X, $W
  $log_word $W
  $log_word $X
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
  call &__HEADER_COMMA
  $NEXT

__HEADER_COMMA:
  ; r0: str ptr, r1: str len
  ; save working registers
  push r2 ; DP address
  push r3 ; DP value
  push r4 ; LATEST address
  push r5 ; LATEST value
  push r6 ; flags/length
  push r7 ; current word char
  ; init registers
  la r2, &var_DP
  lw r3, r2
  la r4, &var_LATEST
  lw r5, r4
  ; align DP, I want words aligned
  $align4 r3
  ; store LATEST as a link value of new word
  stw r3, r5
  mov r5, r3
  stw r4, r5
  ; and move DP to next cell
  add r3, $CELL
  ; save name crc
  push r0
  push r1
  call &strcrc
  sts r3, r0
  pop r1
  pop r0
  ; and move DP to next position which is only a half-cell further
  add r3, $HALFCELL
  ; save flags
  li r6, 0
  stb r3, r6
  ; and move 1 byte further - our ptr will be then 1 byte before next cell-aligned address
  inc r3
  ; save unaligned length ...
  stb r3, r1
  ; and again, move 1 byte further - now, this address should be cell-aligned, 8 bytes from the beginning of the word
  inc r3
  ; copy word name, using its original length
  mov r6, r1
__HEADER_COMMA_loop:
  lb r7, r0
  stb r3, r7
  inc r3
  inc r0
  dec r6
  bnz &__HEADER_COMMA_loop
  ; align DP - this will add padding bytes to name automagicaly
  $align4 r3
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
  call &__COMMA
  $NEXT

__COMMA:
  push r1 ; DP address
  push r2 ; DP value
  la r1, &var_DP
  lw r2, r1
  stw r2, r0
  add r2, $CELL
  stw r1, r2
  pop r2
  pop r1
  ret


$DEFCODE "[", 1, $F_IMMED, LBRAC
  li $W, 0
  la $X, &var_STATE
  stw $X, $W
  $NEXT


$DEFCODE "]", 1, 0, RBRAC
  li $W, 1
  la $X, &var_STATE
  stw $X, $W
  $NEXT


$DEFWORD ":", 1, 0, COLON
  .int &DWORD
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
  la $W, &var_LATEST
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
  .int -8


$DEFWORD "HIDE", 4, 0, HIDE
  .int &DWORD
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

__CMP_true:
  $load_true $W
  push $W
  $NEXT

__CMP_false:
  $load_false $W
  push $W
  $NEXT

$DEFCODE "=", 1, 0, EQU
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  be &__CMP_true
  j &__CMP_false


$DEFCODE "<>", 2, 0, NEQU
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $W, $X
  bne &__CMP_true
  j &__CMP_false


$DEFCODE "0=", 2, 0, ZEQU
  ; ( n -- n )
  pop $W
  cmp $W, 0
  bz &__CMP_true
  j &__CMP_false


$DEFCODE "0<>", 3, 0, ZNEQU
  ; ( n -- n )
  pop $W
  cmp $W, 0
  bnz &__CMP_true
  j &__CMP_false


$DEFCODE "<", 1, 0, LT
  ; ( a b -- n )
  pop $W
  pop $X
  cmp $X, $W
  bl &__CMP_true
  j &__CMP_false


$DEFCODE ">", 1, 0, GT
  pop $W
  pop $X
  cmp $X, $W
  bg &__CMP_true
  j &__CMP_false


$DEFCODE "<=", 2, 0, LE
  pop $W
  pop $X
  cmp $X, $W
  ble &__CMP_true
  j &__CMP_false


$DEFCODE ">=", 2, 0, GE
  pop $W
  pop $X
  cmp $X, $W
  bge &__CMP_true
  j &__CMP_false


$DEFCODE "0<", 2, 0, ZLT
  ; ( n -- flag )
  ; flag is true if and only if n is less than zero
  pop $W
  cmp $W, 0
  bl &__CMP_true
  j &__CMP_false


$DEFCODE "0>", 2, 0, ZGT
  ; ( n -- flag )
  ; flag is true if and only if n is greater than zero
  pop $W
  cmp $W, 0
  bg &__CMP_true
  j &__CMP_false


$DEFCODE "0<=", 3, 0, ZLE
  pop $W
  cmp $W, 0
  ble &__CMP_true
  j &__CMP_false


$DEFCODE "0>=", 3, 0, ZGE
  pop $W
  cmp $W, 0
  bge &__CMP_true
  j &__CMP_false

$DEFCODE "?DUP", 4, 0, QDUP
  pop $W
  cmp $W, 0
  bnz &__QDUP_nonzero
  push 0
  j &__QDUP_next
__QDUP_nonzero:
  push $W
  push $W
__QDUP_next:
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
  call &__DWORD
  inc r0
  lb $W, r0 ; load the first character of next word into W...
  push $W
  $NEXT


$DEFCODE "[CHAR]", 6, $F_IMMED, BRACKETCHAR
  call &__DWORD
  inc r0
  lb $W, r0
  la r0, &LIT
  call &__COMMA
  mov r0, $W
  call &__COMMA
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
  $align4 $FIP    ; align FIP
  $NEXT

$DEFCODE "CQUOTE_LITSTRING", 9, 0, CQUOTE_LITSTRING
  ; ( -- c-addr )
  push $FIP       ; push c-addr
  lb $W, $FIP     ; load string length
  inc $FIP        ; skip length
  add $FIP, $W    ; skip string
  $align4 $FIP    ; align FIP
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
  be &__PAREN_LOOP_next
  $pushrsp $X
  $pushrsp $W
  lw $W, $FIP
  add $FIP, $W
  $NEXT
__PAREN_LOOP_next:
  add $FIP, $CELL
  $NEXT


$DEFCODE "(+LOOP)", 7, 0, PAREN_PLUSLOOP
  $poprsp $W ; index
  $poprsp $X ; control
  pop $Y     ; increment N
  bs &__PAREN_PLUSLOOP_dec
  add $W, $Y
  cmp $W, $X
  bg &__PAREN_PLUSLOOP_next
  j &__PAREN_PLUSLOOP_iter
__PAREN_PLUSLOOP_dec:
  add $W, $Y
  cmp $W, $X
  bl &__PAREN_PLUSLOOP_next
__PAREN_PLUSLOOP_iter:
  $pushrsp $X
  $pushrsp $W
  lw $W, $FIP
  add $FIP, $W
  $NEXT
__PAREN_PLUSLOOP_next:
  add $FIP, $CELL
  $NEXT


$DEFCODE "UNLOOP", 6, 0, UNLOOP
  add $RSP, 8 ; CELL * 2
  $NEXT


$DEFCODE "I", 1, 0, I
  lw $W, $RSP
  push $W
  $NEXT


$DEFCODE "J", 1, 0, J
  lw $W, $RSP[8]
  push $W
  $NEXT


;
; Constants
;
$DEFCODE "VERSION", 7, 0, VERSION
  push $DUCKY_VERSION
  $NEXT

$DEFCODE "R0", 2, 0, RZ
  li $W, 0xFE00
  liu $W, 0xFFFF
  push $W
  $NEXT

$DEFCODE "DOCOL", 5, 0, __DOCOL
  la $W, &DOCOL
  push $W
  $NEXT

$DEFCODE "F_IMMED", 7, 0, __F_IMMED
  push $F_IMMED
  $NEXT

$DEFCODE "F_HIDDEN", 8, 0, __F_HIDDEN
  push $F_HIDDEN
  $NEXT

$DEFCODE "TRUE", 4, 0, TRUE
  $push_true $W
  $NEXT

$DEFCODE "FALSE", 5, 0, FALSE
  $push_false $W
  $NEXT

$DEFCODE "DODOES", 6, 0, __DODOES
  la $W, &DODOES
  push $W
  $NEXT


; Include non-kernel words
 .include "forth/ducky-forth-words.asm"
 .include "forth/double-cell-ints.asm"


$DEFCODE "\\\\", 1, $F_IMMED, BACKSLASH
  la $W, &input_buffer_length
  lw $W, $W
  la $X, &input_buffer_index
  stw $X, $W
  $NEXT


$DEFCODE "HERE", 4, 0, HERE
  la $W, &var_DP
  lw $W, $W
  push $W
  $NEXT


$DEFCODE "CRASH", 5, $F_IMMED, CRASH
  hlt 0x4FFF


;
; The last command - if it's not the last one, modify initial value of LATEST
;
$DEFCODE "BYE", 3, 0, BYE
  la r0, &bye_message
  call &writes

  li r0, 0
  call &halt


;
; Section boundary pivots
;
  .section .data

  .align 4

  .type data_boundary_last, int
  .int 0xDEADBEEF

  .section .rodata

  .align 4

  .type rodata_boundary_last, int
  .int 0xDEADBEEF

  .section .text
text_boundary_last:
  ret
