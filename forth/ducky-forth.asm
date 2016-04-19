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
.include "hdt.asm"


  .text

  ; This is where bootloader jump to, main entry point
_entry:
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

  .type __build_stamp_length, byte
  .byte 57

  .type __build_stamp, string
  .string "$BUILD_STAMP"

  .type bye_message, string
  .string "\r\nBye.\r\n"

  .text


;
; void halt(u32_t exit_code)
;
halt:
  hlt r0


memset:
  cmp r1, 0
__memset_loop:
  bz &__memset_finished
  stb r0, r2
  inc r0
  dec r1
  j &__memset_loop
__memset_finished:
  ret


memzero:
  push r2
  li r2, 0x00
  call &memset
  pop r2
  ret


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
; void write_input_buffer(void)
;
; Write content of internal input buffer to standard terminal output, surrounded
; by pre- ad post-fix for better readability.
;
write_input_buffer:
  push r0
  push r1
  ; prefix
  la r0, &__buffer_prefix
  call &writes
  ; input buffer
  la r0, &input_buffer_address
  lw r0, r0
  la r1, &input_buffer_length
  lw r1, r1
  call &write
  ; postfix + new line
  la r0, &__buffer_postfix
  call &writesln
  pop r1
  pop r0
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
  la r0, &__buffer_prefix
  call &writes
  ; word buffer
  la r0, &word_buffer
  la r1, &word_buffer_length
  lb r1, r1
  call &write
  ; postfix + new line
  la r0, &__buffer_postfix
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
  ; Flush PTE cache
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

  la r0, &rodata_boundary_first
  la r1, &rodata_boundary_last
  call &__relocate_section

  la r0, &data_boundary_first
  la r1, &data_boundary_last
  call &__relocate_section

  li r0, $USERSPACE_BASE
  li r1, $BOOT_LOADER_ADDRESS
  add r0, r1
  mov r1, r0
  add r1, $USERSPACE_SIZE
  call &__relocate_section

  ret


;
; void boot_phase1(void) __attribute__((noreturn))
;
; This is the first phase of kernel booting process. Its main goal is to
; relocate kernel sections to the beggining of the address space. Before
; moving anything the beginning of memory space we have to process HDT,
; save interesting information for later, just in case we'd need some.
; And we will...
;
boot_phase1:
  ; First, turn of debugging. We have no stack, we can't call __vmdebug_off.
  ;li r0, 0x00
  ;li r1, 0x01
  ;int 18

  ; Now, walk through HDT, and save interesting info
  li r0, $BOOT_HDT_ADDRESS             ; r0 will be our HDT pointer
  lw r1, r0
  li r2, 0x6F70
  liu r2, 0x4D5E
  cmp r1, r2
  bne &__ERR_malformed_HDT             ; HDT header magic is bad
  add r0, $WORD_SIZE

  lw r1, r0                            ; r1 counts number of remaining entries
  add r0, $WORD_SIZE

__boot_hdt_loop:
  cmp r1, 0x00
  bz &__boot_hdt_loop_end

  ls r2, r0                            ; entry type
  add r0, $SHORT_SIZE
  ls r3, r0                            ; entry length
  add r0, $SHORT_SIZE

  cmp r2, $HDT_ENTRY_CPU
  bne &__boot_hdt_loop_test_memory
  j &__boot_hdt_loop_goon

__boot_hdt_loop_test_memory:
  cmp r2, $HDT_ENTRY_MEMORY
  bne &__boot_hdt_loop_goon

  lw r4, r0                            ; read memory size, and save it
  la r5, &memory_size
  stw r5, r4

  ; fall through to 'go on' branch

__boot_hdt_loop_goon:
  sub r0, $SHORT_SIZE                  ; undo pointer moves, and point at the first byte of current entry
  sub r0, $SHORT_SIZE
  add r0, r3                           ; and point at the first byte of next entry by adding the current entry size to the pointer
  dec r1
  j &__boot_hdt_loop

__boot_hdt_loop_end:

  ; Setup stack, using the next-to-last memory page
  ; If the stack is supposed to be on next-to-last page, the initial SP is the base address of the last page...
  la sp, &memory_size
  lw sp, sp
  li r0, $PAGE_MASK
  liu r0, 0xFFFF
  and sp, r0

  ; Now there's nothing blocking us from relocating our sections to more convenient place
  call &__relocate_sections

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

  ;
  ; LPF - Last Page Frame, base address of the last page of memory
  ;
  ; +--------------------+ <- 0x00000000
  ; | Initial IVT        |
  ; +--------------------+ <- 0x00000100
  ; | HDT                |
  ; +--------------------+ <- 0x00000200
  ; |                    |
  ; +--------------------+
  ; ...
  ; +
  ; |
  ; +                    +
  ; | Log stack          |
  ; +--------------------+ <- LSP
  ; | RTC stack          |
  ; +--------------------+
  ; | Dummy IVT stack    |
  ; +--------------------+
  ; | Return stack       |
  ; +--------------------+ <- RSP
  ; | Stack              |
  ; +--------------------+ <- LPF; SP
  ; | Our IVT            |
  ; +--------------------+
  ;

  ; r11 will hold the LPF, as a reference point
  la r11, &memory_size
  lw r11, r11
  li r0, $PAGE_MASK
  liu r0, 0xFFFF
  and r11, r0
  sub r11, $PAGE_SIZE

  ; r10 is our current page pointer
  mov r10, r11

  ; Reset stack, just in case there are some leftovers on it - we won't need them anymore
  mov sp, r10
  sub r10, $PAGE_SIZE
  la r9, &var_SZ
  stw r9, sp
.ifdef FORTH_TIR
  ; Init TOS
  li $TOS, 0xBEEF
  liu $TOS, 0xDEAD
.endif

  ; Return stack
  mov $RSP, r10
  sub r10, $PAGE_SIZE
  la r9, &rstack_top
  stw r9, $RSP

  ; IVT
  mov r9, r10                          ; RTC SP
  sub r10, $PAGE_SIZE
  mov r8, r10                          ; Keyboard SP
  sub r8, $PAGE_SIZE
  mov r7, r10                          ; dummy SP
  sub r10, $PAGE_SIZE

  mov r0, r11
  ctw $CONTROL_IVT, r0

  ; init all entries to fail-safe
  la r2, &failsafe_isr

  mov r1, r0
  add r1, $PAGE_SIZE
__boot_phase2_ivt_failsafe_loop:
  stw r0, r2
  add r0, $INT_SIZE
  stw r0, r7
  add r0, $INT_SIZE
  cmp r0, r1
  bne &__boot_phase2_ivt_failsafe_loop

  mov r0, r11

  ; set the first entry to RTC ISR
  la r2, &rtc_isr
  stw r0, r2
  add r0, $INT_SIZE
  stw r0, r9
  add r0, $INT_SIZE

  ; set the second entry to NOP ISR for keyboard
  la r2, &nop_isr
  stw r0, r2
  add r0, $INT_SIZE
  stw r0, r8
  add r0, $INT_SIZE

.ifdef FORTH_DEBUG
  ; Log stack
  mov $LSP, r10
  sub r10, $PAGE_SIZE
.endif

  ; init LATEST
  la r0, &var_LATEST
  la r1, &name_BYE
  stw r0, r1

  ; init pictured numeric output buffer
  call &__reset_pno_buffer

  ; init words' crcs
  call &init_crcs

  ; give up the privileged mode
  ; lpm
  sti

  ; and boot the FORTH itself...
  la $FIP, &cold_start
  $NEXT


;
; void failsafe_isr(void) __attribute__((noreturn))
;
; Fail-safe interrupt service routine - if this interrupt
; gets triggered, kill kernel.
;
  .section .rodata
  .type __ERR_unhandled_irq_message, string
  .string "\r\nERROR: $ERR_UNHANDLED_IRQ: Unhandled irq\r\n"

failsafe_isr:
  la r0, &__ERR_unhandled_irq_message
  li r1, $ERR_UNHANDLED_IRQ
  j &__ERR_die


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
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, $W
.else
  push $W
.endif
  $NEXT


  .section .rodata
  .align 4
cold_start:
  ;.int &WELCOME
  .int &QUIT


  .section .data

  .align 4
  .type data_boundary_first, int
  .int 0xDEADBEEF

  .type rstack_top, int
  .int 0xFFFFFE00

  .type jiffies, int
  .int 0x00000000

  .type memory_size, int
  .int 0xFFFFFFFF

  ; User data area
  ; Keep it in separate section to keep it aligned, clean, unpoluted
  .section .userspace, rwblg
  .space $USERSPACE_SIZE


  .set link, 0

;
; Variables
;
$DEFVAR "ECHO", 4, 0, ECHO, 0
$DEFVAR "UP", 2, 0, UP, $USERSPACE_BASE
$DEFVAR "STATE", 5, 0, STATE, 0
$DEFVAR "DP", 2, 0, DP, $USERSPACE_BASE
$DEFVAR "LATEST", 6, 0, LATEST, &name_BYE
$DEFVAR "S0", 2, 0, SZ, 0xFFFFFF00
$DEFVAR "BASE", 4, 0, BASE, 10
$DEFVAR "SOURCE-ID", 9, 0, SOURCE_ID, 0
$DEFVAR "SHOW-PROMPT", 11, 0, SHOW_PROMPT, 0


$DEFWORD "WELCOME", 7, 0, WELCOME
  .int &CQUOTE_LITSTRING
  .int 0x53455409
  .int 0x4F4D2D54
  .int 0x00004544
  .int &FIND
  .int &SWAP
  .int &DROP
  .int &NOT
  .int &ZBRANCH
  .int 0x00000078
  .int &SQUOTE_LITSTRING
  .int 0x63754413
  .int 0x4F46796B
  .int 0x20485452
  .int 0x53524556
  .int 0x204E4F49
  .int &TELL
  .int &VERSION
  .int &DOT
  .int &CR
  .int &SQUOTE_LITSTRING
  .int 0x69754206
  .int 0x0020646C
  .int &TELL
  .int &BUILD_STAMP
  .int &TYPE
  .int &CR
  .int &UNUSED
  .int &DOT
  .int &SQUOTE_LITSTRING
  .int 0x4C45430F
  .int 0x5220534C
  .int 0x49414D45
  .int 0x474E494E
  .int &TELL
  .int &CR
  .int &TRUE
  .int &SHOW_PROMPT
  .int &STORE
  .int &TRUE
  .int &ECHO
  .int &STORE
  .int &EXIT


$DEFCODE "BUILD-STAMP", 11, 0, BUILD_STAMP
  ; ( -- addr u )
.ifdef FORTH_TIR
  push $TOS
  la $X, &__build_stamp_length
  lb $TOS, $X
  inc $X
  push $X
.else
  la $W, &__build_stamp_length
  lb $X, $W
  inc $W
  push $W
  push $X
.endif
  $NEXT


$DEFCODE "VMDEBUGON", 9, $F_IMMED, VMDEBUGON
  ; ( -- )
  call &__vmdebug_on
  $NEXT


$DEFCODE "VMDEBUGOFF", 10, $F_IMMED, VMDEBUGOFF
  call &__vmdebug_off
  $NEXT


;
; Buffer printing - asorted helper strings
;
  .section .rodata

  .type __input_buffer_label, string
  .string "Input buffer: "

  .type __word_buffer_label, string
  .string "Word buffer: "

  .type __buffer_prefix, string
  .string ">>>"

  .type __buffer_postfix, string
  .string "<<<"


;****************************
;
; Ambiguous condition handling
;
;****************************

;
; void __ERR_die(char *msg, i32_t exit_code) __attribute__((noreturn))
;
; Generic fatal error handler
  .text

__ERR_die:
  call &writes
  hlt r1


;
; void __ERR_print_input(char *word, u32_t length)
;
; Prints input buffer and word
;
__ERR_print_input:
  push r0
  push r1
  la r0, &__input_buffer_label
  call &writes
  call &write_input_buffer
  la r0, &__word_buffer_label
  call &writes
  la r0, &__buffer_prefix
  call &writes
  pop r1
  pop r0
  call &write
  la r0, &__buffer_postfix
  call &writesln
  ret



;
; void __ERR_undefined_word(char *s, u32_t length) __attribute__((noreturn))
;
; Raised when word is not in dictionary nor a number.
;
  .section .rodata
  .type __ERR_undefined_word_message, string
  .string "\r\nERROR: $ERR_UNDEFINED_WORD: Undefined word\r\n"

  .text

__ERR_undefined_word:
  push r0
  push r1
  la r0, &__ERR_undefined_word_message
  call &writes
  pop r1
  pop r0
  call &__ERR_print_input
  li r0, $ERR_UNDEFINED_WORD
.ifdef FORTH_FAIL_ON_UNDEF
  j &halt
.else
  ret
.endif


;
; void __ERR_no_interpretation_semantics(void) __attribute__((noreturn))
;
; Raised when word with undefined interpretation semantics is executed
; in interpretation state.
;
  .section .rodata
  .type __ERR_no_interpretation_semantics_message, string
  .string "\r\nERROR: $ERR_NO_INTERPRET_SEMANTICS: Word has undefined interpretation semantics\r\n"

  .text

__ERR_no_interpretation_semantics:
  la r0, &__ERR_no_interpretation_semantics_message
  call &writes
  call &__ERR_print_input
  li r0, $ERR_NO_INTERPRET_SEMANTICS
  j &halt


;
; void __ERR_malformed_HDT(void) __attribute__((noreturn))
;
; Raised when HDT is malformed.
;
  .text

__ERR_malformed_HDT:
  li r0, $ERR_MALFORMED_HDT
  j &halt


;
; void __ERR_unknown(void) __attribute__((noreturn))
;
; Raise when otherwise unhandled error appears.
;
  .section .rodata
  .type __ERR_unknown_message, string
  .string "\r\nERROR: $ERR_UNKNOWN: Unknown error happened\r\n"

  .text

__ERR_unknown:
  la r0, &__ERR_unknown_message
  li r1, $ERR_UNKNOWN
  j &__ERR_die


;
; Default prompt
;
  .section .rodata
  .type __default_prompt, string
  .string "  ok\r\n"



$DEFCODE "PROMPT", 6, 0, PROMPT
  ; ( flag -- )
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
  call &__write_prompt
  $NEXT

__write_prompt:
  cmp r0, r0
  bz &__write_prompt_quit
  la r0, &__default_prompt
  call &writes
__write_prompt_quit:
  ret


;****************************
;
; Terminal IO routines and words
;
;****************************

  .data

  ; word_buffer lies right next to word_buffer_length, pretending it's
  ; a standard counted string <length><chars...>
  .type word_buffer_length, byte
  .byte 0

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


;
; char __read_stdin(void)
;
; Read 1 character from stdin (terminal). If no characters are available,
; block until new one arrives.
;
__read_stdin:
  inb r0, $KBD_PORT_DATA
  cmp r0, 0xFF
  be &__read_stdin_wait
  ret
__read_stdin_wait:
  ; This is a small race condition... What if new key
  ; arrives after inb and before idle? We would be stuck until
  ; the next key arrives (and it'd be Enter, nervously pressed
  ; by programmer while watching machine "doing nothing")
  idle
  j &__read_stdin



;
; void __write_stdout(char c)
;
; Write 1 character to stdout (terminal).
;
__write_stdout:
  outb $TTY_PORT_DATA, r0
  ret


;
; u32_t __read_line(char *buff, u32_t max)
;
; Read line of maximum MAX characters from stdin, and store it in BUFF.
; Returns number of read characters.
;
__read_line:
  cmp r1, 0x00                         ; zero maximal length is an ambiguous condition
  bz &__ERR_unknown
  push r2                              ; counter
  push r3                              ; character
  push r4                              ; echo?
  la r4, &var_ECHO
  lw r4, r4
  li r2, 0x00                          ; reset counter
  cmp r1, 0x00                         ; set flags properly to allow check in the loop
__read_line_loop:
  bz &__read_line_quit                 ; if 0 chars remains in buffer, quit
  inb r3, $KBD_PORT_DATA
  cmp r3, 0xFF
  be &__read_line_wait
  cmp r4, 0x00
  bz &__read_line_tests
  outb $TTY_PORT_DATA, r3
__read_line_tests:
  cmp r3, 0x0A                         ; nl
  be &__read_line_quit
  cmp r3, 0x0D                         ; cr
  be &__read_line_quit
  stb r0, r3
  inc r0
  inc r2
  dec r1
  j &__read_line_loop
__read_line_quit:
  mov r0, r2
  pop r4
  pop r3
  pop r2
  ret
__read_line_wait:
  idle
  j &__read_line_loop


;
; char __read_input(void)
;
; Read 1 character from input buffer. Return character, or 0x00 when no input
; is available.
;
__read_input:
  push r1
  push r2
  la r0, &input_buffer_length
  lw r0, r0
  la r1, &input_buffer_index
  lw r2, r1
  cmp r2, r0
  be &__read_input_end
  la r0, &input_buffer_address
  lw r0, r0
  add r0, r2
  lb r0, r0
  inc r2
  stw r1, r2
  pop r2
  pop r1
  ret
__read_input_end:
  li r0, 0x00
  pop r2
  pop r1
  ret

;
; void __input_stack_push(void)
;
; Save current state of input buffer to the top of the input stack.
;
__input_stack_push:
  push r0                              ; &input_stack_ptr
  push r1                              ; pointer
  push r2                              ; value

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
  ; STATE
  la r2, &var_STATE
  lw r2, r2
  stw r1, r2
  add r1, $CELL
  ; SOURCE-ID
  la r2, &var_SOURCE_ID
  lw r2, r2
  stw r1, r2
  add r1, $CELL

  stw r0, r1

  pop r2
  pop r1
  pop r0

  ret

;
;
;
__input_stack_pop:
  push r0
  push r1
  push r2
  push r3

  la r0, &input_stack_ptr
  lw r1, r0

  ; SOURCE-ID
  sub r1, $CELL
  la r2, &var_SOURCE_ID
  lw r3, r1
  stw r2, r3
  ; STATE
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


;
; void __refill_input(void)
;
; Read one line from input source, and store it in input buffer, making it
; the new input.
;
__refill_input:
  push r0
  push r1

  ; Since the current input source is obviously empty, check the input stack,
  ; and restore the previous input source if possible.
  la r0, &input_stack_ptr
  lw r0, r0
  la r1, &input_stack
  cmp r0, r1
  be &__refill_input_stdin

  ; restore the previous input source
  call &__input_stack_pop
  pop r1
  pop r0
  ret

__refill_input_stdin:
  ; get a line from stdin
  la r0, &input_buffer
  li r1, $INPUT_BUFFER_SIZE
  call &__read_line

  ; save length
  la r1, &input_buffer_length
  stw r1, r0

  ; reset index
  la r0, &input_buffer_index
  li r1, 0x00
  stw r0, r1

  pop r1
  pop r0
  ret


;
; char *__read_word(char delimiter)
;
; Read characters from input buffer. Skip leading delimiters, then copy the following
; characters into word buffer, until raching the end of input buffer or the delimiter
; is encountered. Resets word_buffer_index, and sets word_buffer_length properly.
; If the input buffer is empty when __read_word is called, word buffer length is set
; to zero.
;
__read_word:
  ; delimiter -- c-addr
  push r3
  mov r3, r0 ; save delimiter
__read_word_read_input:
  ; first, skip leading delimiters
  call &__read_input
  cmp r0, 0x00
  bz &__read_word_eof
  cmp r0, r3
  be &__read_word_read_input
  ; also, skip leading white space - except the space itself...
  cmp r0, 0x20
  bl &__read_word_read_input
  push r1
  push r2
  la r1, &word_buffer
__read_word_store_char:
  stb r1, r0
  inc r1
  call &__read_input
  cmp r0, 0x00 ; end of input buffer?
  be &__read_word_save
  cmp r0, r3   ; separator?
  be &__read_word_save
  cmp r0, 0x20 ; space???
  bl &__read_word_save
  j &__read_word_store_char
__read_word_save:
  la r2, &word_buffer
  sub r1, r2
  la r0, &word_buffer_length
  stb r0, r1
  pop r2
  pop r1
  pop r3
  ret
__read_word_eof:
  ; no available data in input buffer
  la r0, &word_buffer_length
  li r3, 0x00
  stb r0, r3
  pop r3
  ret


;
; char * __read_word_with_refill(char delimiter)
;
__read_word_with_refill:
  push r2
  push r3
  mov r3, r0
__read_word_with_refill_loop:
  call &__read_word
  lb r2, r0
  bz &__read_word_with_refill_refill
  pop r3
  pop r2
  ret
__read_word_with_refill_refill:
  la r0, &var_SHOW_PROMPT
  lw r0, r0
  call &__write_prompt
  call &__refill_input
  mov r0, r3
  j &__read_word_with_refill_loop


;
; char *__read_dword(void)
;
; __read_word with space as a delimiter.
;
__read_dword:
  li r0, 0x20
  j &__read_word


__read_dword_with_refill:
  li r0, 0x20
  j &__read_word_with_refill


$DEFCODE "WORD", 4, 0, WORD
  ; ( char "<chars>ccc<char>" -- c-addr )
.ifdef FORTH_TIR
  mov r0, $TOS
  call &__read_word_with_refill
  mov $TOS, r0
.else
  pop r0
  call &__read_word_with_refill
  push r0
.endif
  $NEXT


$DEFCODE "DWORD", 5, 0, DWORD
  ; ( "<chars>ccc<char>" -- c-addr )
  ; like WORD but with space as a delimiter ("default WORD")
.ifdef FORTH_TIR
  call &__read_dword_with_refill
  push $TOS
  mov $TOS, r0
.else
  call &__read_dword_with_refill
  push r0
.endif
  $NEXT


$DEFCODE "PARSE", 5, 0, PARSE
  ; ( char "ccc<char>" -- c-addr u )
  ; parse input buffer, no copying, no modifications

.ifdef FORTH_TIR
  mov $Y, $TOS
.else
  pop $Y
.endif

  ; init pointer to the parsed word
  ; right now, it points to the first character we're gonna read, which
  ; may be invalid, but this won't matter if a) word is parsed, X will
  ; get proper value, b) there's no word, TOS will be zero
  la $W, &input_buffer_address
  lw $W, $W
  la $X, &input_buffer_index
  add $W, $X
  li $W, 0                             ; length counter

  ; skip over leading delimiters
__PARSE_read_leading_input:
  call &__read_input
  cmp r0, 0x00                         ; no input left?
  bz &__PARSE_quit
  cmp r0, $Y                           ; delimiter?
  be &__PARSE_read_leading_input
  cmp r0, 0x20                         ; space?
  be &__PARSE_read_leading_input

  ; now parse the word
  la $W, &input_buffer_address
  lw $W, $W
  la $X, &input_buffer_index
  add $W, $X                           ; now, X has address of the first valid character of a word
  li $W, 0                             ; length counter
__PARSE_read_word:
  call &__read_input
  cmp r0, 0x00                         ; no input left?
  bz &__PARSE_quit
  cmp r0, $Y                           ; delimiter? quit
  be &__PARSE_quit
  inc $W
  j &__PARSE_read_word

__PARSE_quit:
  push $X
.ifdef FORTH_TIR
  mov $TOS, $W
.else
  push $W
.endif
  $NEXT


$DEFCODE "ACCEPT", 6, 0, ACCEPT
  ; ( c-addr +n1 -- +n2 )
.ifdef FORTH_TIR
  mov r1, $TOS
  pop r0
  call &__read_line
  mov $TOS, r0
.else
  pop r1
  pop r0
  call &__read_line
  push r0
.endif
  $NEXT


$DEFCODE "REFILL", 6, 0, REFILL
  ; ( -- flag )
  call &__refill_input
.ifdef FORTH_TIR
  push $TOS
  $load_true $TOS
.else
  $push_true r0
.endif
  $NEXT


$DEFCODE "KEY", 3, 0, KEY
  ; ( -- n )
  call &__read_input
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, r0
.else
  push r0
.endif
  $NEXT


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
  call &__write_stdout
  $NEXT


$DEFCODE "EVALUATE", 8, 0, EVALUATE
  ; ( c-addr u -- )
.ifdef FORTH_TIR
  mov r1, $TOS
  pop r0
  pop $TOS
  call &__EVALUATE
.else
  pop r1
  pop r0
  call &__EVALUATE
.endif
  $NEXT

;
; void __EVALUATE(char *buffer, u32_t length)
;
__EVALUATE:
  ; save current input state
  call &__input_stack_push

  push r2
  push r3

  ; set SOURCE-ID to -1
  la r2, &var_SOURCE_ID
  li r3, -1
  stw r2, r3

  ; make the string new input buffer
  la r2, &input_buffer_address
  stw r2, r0
  la r2, &input_buffer_length
  stw r2, r1

  ; set >IN to zero
  la r2, &input_buffer_index
  li r0, 0x00
  stw r2, r0

  ; and interpret...
  pop r3
  pop r2
  ret


$DEFCODE ">IN", 3, 0, TOIN
  ; ( -- addr )
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &input_buffer_index
.else
  la $W, &input_buffer_index
  push $W
.endif
  $NEXT


$DEFCODE "TYPE", 4, 0, TYPE
  ; ( address length -- )
.ifdef FORTH_TIR
  mov r1, $TOS
  pop r0
  pop $TOS
.else
  pop r1
  pop r0
.endif
  call &write
  $NEXT


$DEFCODE "SOURCE", 6, 0, SOURCE
  ; ( -- address length )
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &input_buffer_address
  lw $TOS, $TOS
  push $TOS
  la $TOS, &input_buffer_length
  lw $TOS, $TOS
.else
  la $W, &input_buffer_address
  lw $W, $W
  push $W
  la $W, &input_buffer_length
  lw $W, $W
  push $W
.endif
  $NEXT


$DEFCODE "NUMBER", 6, 0, NUMBER
  ; ( address length -- number unparsed_chars )
.ifdef FORTH_TIR
  mov r1, $TOS
  pop r0
  call &__NUMBER
  push r0
  mov $TOS, r1
.else
  pop r1
  pop r0
  call &__NUMBER
  push r0
  push r1
.endif
  $NEXT


.macro __NUMBER_getch:
  lb r4, r3
  inc r3
  dec r1
.end

__NUMBER:
  cmp r1, r1                           ; if the string is empty, leave
  bz &__NUMBER_quit_noclean

  ; setup working registers
  push r2                              ; BASE
  push r3                              ; char ptr
  push r4                              ; current char
  push r5                              ; negative flag
  li r2, 0                             ; set BASE register to zero, to signal we don't know it yet
  mov r3, r0
  li r0, 0
  li r5, 0                             ; so far, number is non-negative

  ; read first char, and check if it's a prefix
  $__NUMBER_getch
  cmp r4, 0x23                         ; # - decimal
  be &__NUMBER_base_decimal
  cmp r4, 0x26                         ; & - decimal
  be &__NUMBER_base_decimal
  cmp r4, 0x24                         ; $ - hexadecimal
  be &__NUMBER_base_hexadecimal
  cmp r4, 0x25                         ; % - binary
  be &__NUMBER_base_binary
  cmp r4, 0x27                         ; ' - number is the next char's ASCII code
  be &__NUMBER_ascii
  la r2, &var_BASE                     ; no prefix - use default base
  lw r2, r2

__NUMBER_sign_test:
  ; we have a character to examine - prefix branches fetched a new one
  cmp r4, 0x2D                         ; '-'
  bne &__NUMBER_convert_digit
  li r5, 1                             ; mark as negative
  cmp r1, r1                           ; if there are no remaining chars, we got only '-' - that's bad, quit
  bnz &__NUMBER_loop
__NUMBER_quit:
  pop r5
  pop r4
  pop r3
  pop r2
__NUMBER_quit_noclean:
  ret

__NUMBER_base_decimal:
  li r2, 10
  j &__NUMBER_base_known

__NUMBER_base_hexadecimal:
  li r2, 16
  j &__NUMBER_base_known

__NUMBER_base_binary:
  li r2, 2
  j &__NUMBER_base_known

__NUMBER_base_known:
  ; read next character after prefix
  $__NUMBER_getch
  j &__NUMBER_sign_test

__NUMBER_ascii:
  $__NUMBER_getch
  mov r0, r4                           ; converting to char's ASCII code is quite easy...
  cmp r1, r1                           ; if we're out of chars, quit
  bz &__NUMBER_quit
  cmp r1, 1                            ; optional trailing '
  bne &__NUMBER_fail                   ; there are still some other chars after 'c' - that's bad, quit
  $__NUMBER_getch
  cmp r4, 0x27                         ; trailing char must be ', otherwise it's bad
  bne &__NUMBER_fail
  j &__NUMBER_quit

__NUMBER_trailing_tick:
  dec r1

__NUMBER_loop:
  cmp r1, r1
  bz &__NUMBER_negate
  $__NUMBER_getch

__NUMBER_convert_digit:
  ; if char is lower than '0' then it's bad - quit
  sub r4, 0x30
  bs &__NUMBER_fail
  ; if char is lower than 10, it's a digit, convert it according to base
  cmp r4, 10
  bl &__NUMBER_check_base
  ; if it's between '9' and 'A', it's bad - quit
  sub r4, 17 ; 'A' - '0' = 17
  bs &__NUMBER_fail
  ; if it's 'a' and above, convert to upper case
  cmp r4, 32
  bl &__NUMBER_shift_digit
  sub r4, 32
  ; and shift it above 9
__NUMBER_shift_digit:
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
  cmp r5, r5
  bz &__NUMBER_quit
  not r0
  inc r0
  j &__NUMBER_quit


.ifdef FORTH_DEBUG_FIND
  .section .rodata

  .type find_debug_header, string
  .string "\r\n---------------------------\r\nFIND WORD:\r\n"
.endif

$DEFCODE "FIND", 4, 0, FIND
  ; ( c-addr -- 0 0 | xt 1 | xt -1 )
.ifdef FORTH_TIR
  mov r0, $TOS
  inc r0
  mov r1, $TOS
  lb r1, r1
.else
  pop r1
  mov r0, r1
  inc r0
  lb r1, r1
.endif
  call &__FIND
  cmp r0, 0
  bz &__FIND_notfound
  push r1
  call &__TCFA
  pop r1
.ifdef FORTH_TIR
  push r0
  mov $TOS, r1
.else
  push r0
  push r1
.endif
  j &__FIND_next
__FIND_notfound:
.ifdef FORTH_TIR
  push 0x00
  li $TOS, 0x00
.else
  push 0
  push 0
.endif
__FIND_next:
  $NEXT


__FIND:
.ifdef FORTH_DEBUG_FIND
  push r0
  la r0, &find_debug_header
  call &writesln
  pop r0
  push r0
  push r1
  call &__ERR_print_input
  pop r1
  pop r0
.endif

  ; r0 - address
  ; r1 - length

  cmp r1, r1
  bz &__FIND_fail_noclean


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
__FIND_fail_noclean:
  li r0, 0
  li r1, 0
  ret


$DEFCODE "'", 1, $F_IMMED, TICK
  ; ( "<spaces>name" -- xt )
  call &__read_dword_with_refill
  $unpack_word_for_find
  call &__FIND
  call &__TCFA
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, r0
.else
  push r0
.endif
  $NEXT


$DEFCODE "[']", 3, 0, BRACKET_TICK
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $FIP
.else
  lw $W, $FIP
  push $W
.endif
  add $FIP, $CELL
  $NEXT


$DEFCODE ">CFA", 4, 0, TCFA
  ; ( address -- address )
.ifdef FORTH_TIR
  mov r0, $TOS
  call &__TCFA
  mov $TOS, r0
.else
  pop r0
  call &__TCFA
  push r0
.endif
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
.ifdef FORTH_TIR
  mov $W, $TOS
  pop $TOS
.else
  pop $W
.endif
  lw $X, $W
  $log_word $W
  $log_word $X
  j $X


$DEFCODE "LIT", 3, 0, LIT
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $FIP
.else
  lw $W, $FIP
  push $W
.endif
  add $FIP, $CELL
  $NEXT


$DEFCODE "HEADER,", 7, 0, HEADER_COMMA
  ; ( c-addr -- )
.ifdef FORTH_TIR
  mov r0, $TOS
  inc r0
  mov r1, $TOS
  lb r1, r1
  pop $TOS
.else
  pop r1
  mov r0, r1
  inc r0
  lb r1, r1
.endif
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
  ; ( x -- )
.ifdef FORTH_TIR
  mov r0, $TOS
  pop $TOS
.else
  pop r0
.endif
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
  or $Y, $F_IMMED
  stb $X, $Y
  $NEXT


$DEFCODE "HIDDEN", 6, 0, HIDDEN
  ; ( word_address -- )
.ifdef FORTH_TIR
  add $TOS, $wr_flags
  lb $X, $TOS
  xor $X, $F_HIDDEN
  stb $TOS, $X
  pop $TOS
.else
  pop $X
  add $X, $wr_flags
  lb $W, $X
  xor $W, $F_HIDDEN
  stb $X, $W
.endif
  $NEXT


$DEFCODE "BRANCH", 6, 0, BRANCH
  ; ( -- )
  lw $W, $FIP
  add $FIP, $W
  $NEXT


$DEFCODE "0BRANCH", 7, 0, ZBRANCH
  ; ( n -- )
.ifdef FORTH_TIR
  mov $W, $TOS
  pop $TOS
  cmp $W, $W
.else
  pop $W
.endif
  bz &code_BRANCH
  add $FIP, $CELL
  $NEXT


$DEFCODE "INTERPRET", 9, 0, INTERPRET
  ; This word is the most inner core of the outer interpreter. It will read
  ; words from input buffer - refilling it when necessary - and execute them
  ;
  ; r10, r11, r12, r13 are used for internal state - it's highly unlikely that other
  ; routines will use these, as they are quite high on the list, so it's unlikely
  ; that they will be pushed and popped by called routines. Also, this word does
  ; not have to take care of saving and restoring registers - as long as we keep
  ; stack clean, and transfer to the word soon enough.

  ; *** Get new word
  li r0, 0x20                ; space is default delimiter
  call &__read_word

  ; if the string has zero length, refill buffer and move on, leave the rest
  ; for next iteration of QUIT
  lb r1, r0
  bz &__interpret_refill

  ; save stuff for later
  inc r0                     ; point to string
  mov r10, r0                ; string address
  mov r11, r1                ; string length
  li r12, 0                  ; "interpret as LIT?" flag

  ; *** Search for the word in the dictionary
  call &__FIND

  ; *** Interpret
  cmp r0, r0                 ; if it's not in dictionary, it must be a number, right?
  bz &__interpret_as_lit

  ; get word's code field address (CFA)
  mov r1, r0                 ; save word address for later
  call &__TCFA
  add r1, $wr_flags          ; get word's flags
  lb r1, r1
  and r1, $F_IMMED           ; if it's an immediate word, execute it no matter what STATE says
  bnz &__interpret_execute
  j &__interpret_state_check

__interpret_as_lit:
  inc r12                    ; mark as LIT

  ; try to parse string as a number
  mov r0, r10
  mov r1, r11
  call &__NUMBER
  cmp r1, r1                 ; non-zero unparsed chars means NaN
  bnz &__interpret_undefined
  mov r1, r0                 ; save number for later
  la r0, &LIT                ; and set "the word" to LIT

__interpret_state_check:
  ; if STATE is zero, execute what we've parsed
  la r13, &var_STATE
  lw r13, r13
  bz &__interpret_execute

  ; otherwise append r0 (our found "word") to current definition
  call &__COMMA

  ; if the word was not LIT, continue with next word
  cmp r12, r12
  bz &__interpret_next

  ; otherwise, pass our parsed number to COMMA
  mov r0, r1
  call &__COMMA

  ; and go to next word...
  j &__interpret_next

__interpret_execute:
  cmp r12, r12               ; LIT has its own mode
  bnz &__interpret_execute_lit

  ; execute the word
  mov $W, r0
  lw $X, r0
  $log_word $W
  $log_word $X
  j $X

__interpret_execute_lit:
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, r1
.else
  push r1
.endif
  $NEXT

__interpret_refill:
  la r0, &var_SHOW_PROMPT
  lw r0, r0
  call &__write_prompt
  call &__refill_input

__interpret_next:
  $NEXT

__interpret_undefined:
  mov r0, r10                          ; pass word to error handler
  mov r1, r11
  call &__ERR_undefined_word
  la r0, &var_STATE
  li r1, 0
  stw r0, r1
  call &__refill_input
  $NEXT



$DEFWORD "QUIT", 4, 0, QUIT
  .int &RZ                             ; reset return stack
  .int &RSPSTORE
  .int &SOURCE_ID
  .int &LIT
  .int 0
  .int &STORE
  .int &LBRAC
  .int &REFILL                         ; do the initial refill
  .int &DROP                           ; drop REFILL's return value
  .int &INTERPRET                      ; refill buffer, read word, execute them
  .int &BRANCH                         ; back to interpret
  .int -8


$DEFCODE "ABORT", 5, 0, ABORT
  la $W, &var_SZ
  lw sp, $W

  ; now this is tricky... jumping to QUIT
  la $W, &QUIT
  lw $X, $W
  j $X


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
.ifdef FORTH_TIR
  $load_true $TOS
.else
  $push_true $W
.endif
  $NEXT

__CMP_false:
.ifdef FORTH_TIR
  $load_false $TOS
.else
  $load_false $W
  push $W
.endif
  $NEXT


$DEFCODE "=", 1, 0, EQU
  ; ( a b -- n )
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $W, $X
.endif
  be &__CMP_true
  j &__CMP_false


$DEFCODE "<>", 2, 0, NEQU
  ; ( a b -- n )
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $W, $X
.endif
  bne &__CMP_true
  j &__CMP_false


$DEFCODE "0=", 2, 0, ZEQU
  ; ( n -- n )
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
.endif
  bz &__CMP_true
  j &__CMP_false


$DEFCODE "0<>", 3, 0, ZNEQU
  ; ( n -- n )
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
.endif
  bnz &__CMP_true
  j &__CMP_false


$DEFCODE "<", 1, 0, LT
  ; ( a b -- n )
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $X, $W
.endif
  bl &__CMP_true
  j &__CMP_false


$DEFCODE ">", 1, 0, GT
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $X, $W
.endif
  bg &__CMP_true
  j &__CMP_false


$DEFCODE "<=", 2, 0, LE
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $X, $W
.endif
  ble &__CMP_true
  j &__CMP_false


$DEFCODE ">=", 2, 0, GE
.ifdef FORTH_TIR
  pop $W
  cmp $W, $TOS
.else
  pop $W
  pop $X
  cmp $X, $W
.endif
  bge &__CMP_true
  j &__CMP_false


$DEFCODE "0<", 2, 0, ZLT
  ; ( n -- flag )
  ; flag is true if and only if n is less than zero
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
  cmp $W, 0
.endif
  bl &__CMP_true
  j &__CMP_false


$DEFCODE "0>", 2, 0, ZGT
  ; ( n -- flag )
  ; flag is true if and only if n is greater than zero
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
  cmp $W, 0
.endif
  bg &__CMP_true
  j &__CMP_false


$DEFCODE "0<=", 3, 0, ZLE
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
  cmp $W, 0
.endif
  ble &__CMP_true
  j &__CMP_false


$DEFCODE "0>=", 3, 0, ZGE
.ifdef FORTH_TIR
  cmp $TOS, 0
.else
  pop $W
  cmp $W, 0
.endif
  bge &__CMP_true
  j &__CMP_false


$DEFCODE "?DUP", 4, 0, QDUP
.ifdef FORTH_TIR
  cmp $TOS, 0
  bnz &__QDUP_nonzero
  li $TOS, 0x00
  $NEXT
__QDUP_nonzero:
  push $TOS
.else
  pop $W
  cmp $W, 0
  bnz &__QDUP_nonzero
  push 0
  $NEXT
__QDUP_nonzero:
  push $W
  push $W
.endif
  $NEXT


;
; Arthmetic operations
;
$DEFCODE "+", 1, 0, ADD
  ; ( a b -- a+b )
.ifdef FORTH_TIR
  pop $W
  add $TOS, $W
.else
  pop $W
  pop $X
  add $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "-", 1, 0, SUB
  ; ( a b -- a-b )
.ifdef FORTH_TIR
  pop $W
  sub $W, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  sub $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "1+", 2, 0, INCR
  ; ( a -- a+1 )
.ifdef FORTH_TIR
  inc $TOS
.else
  pop $W
  inc $W
  push $W
.endif
  $NEXT


$DEFCODE "1-", 2, 0, DECR
  ; ( a -- a-1 )
.ifdef FORTH_TIR
  dec $TOS
.else
  pop $W
  dec $W
  push $W
.endif
  $NEXT


$DEFCODE "2+", 2, 0, INCR2
  ; ( a -- a+2 )
.ifdef FORTH_TIR
  add $TOS, 2
.else
  pop $W
  add $W, 2
  push $W
.endif
  $NEXT


$DEFCODE "2-", 2, 0, DECR2
  ; ( a -- a-2 )
.ifdef FORTH_TIR
  sub $TOS, 2
.else
  pop $W
  sub $W, 2
  push $W
.endif
  $NEXT


$DEFCODE "4+", 2, 0, INCR4
  ; ( a -- a+4 )
.ifdef FORTH_TIR
  add $TOS, 4
.else
  pop $W
  add $W, 4
  push $W
.endif
  $NEXT


$DEFCODE "4-", 2, 0, DECR4
  ; ( a -- a-4 )
.ifdef FORTH_TIR
  sub $TOS, 4
.else
  pop $W
  sub $W, 4
  push $W
.endif
  $NEXT


$DEFCODE "*", 1, 0, MUL
  ; ( a b -- a*b )
.ifdef FORTH_TIR
  pop $W
  mul $TOS, $W
.else
  pop $W
  pop $X
  mul $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "/", 1, 0, DIV
  ; ( a b -- <a / b> )
.ifdef FORTH_TIR
  pop $W
  div $W, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  div $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "MOD", 3, 0, MOD
  ; ( a b -- <a % b> )
.ifdef FORTH_TIR
  pop $W
  mod $W, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  mod $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "/MOD", 4, 0, DIVMOD
  ; ( a b -- <a % b> <a / b> )
.ifdef FORTH_TIR
  pop $W
  mov $X, $W
  div $W, $TOS
  mod $X, $TOS
  push $X
  mov $TOS, $W
.else
  pop $W
  pop $X
  mov $Y, $X
  mod $X, $W
  div $Y, $W
  push $X
  push $Y
.endif
  $NEXT


$DEFCODE "AND", 3, 0, AND
  ; ( x1 x2 -- <x1 & x2> )
.ifdef FORTH_TIR
  pop $W
  and $TOS, $W
.else
  pop $W
  pop $X
  and $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "OR", 2, 0, OR
.ifdef FORTH_TIR
  pop $W
  or $TOS, $W
.else
  pop $W
  pop $X
  or $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "XOR", 3, 0, XOR
.ifdef FORTH_TIR
  pop $W
  xor $TOS, $W
.else
  pop $W
  pop $X
  xor $X, $W
  push $X
.endif
  $NEXT


$DEFCODE "INVERT", 6, 0, INVERT
.ifdef FORTH_TIR
  not $TOS
.else
  pop $W
  not $W
  push $W
.endif
  $NEXT


;
; Parameter stack operations
;

$DEFCODE "DROP", 4, 0, DROP
  ; ( n -- )
.ifdef FORTH_TIR
  pop $TOS
.else
  pop $W
.endif
  $NEXT


$DEFCODE "SWAP", 4, 0, SWAP
  ; ( a b -- b a )
.ifdef FORTH_TIR
  pop $W
  push $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  push $W
  push $X
.endif
  $NEXT


$DEFCODE "DUP", 3, 0, DUP
  ; ( a -- a a )
.ifdef FORTH_TIR
  push $TOS
.else
  pop $W
  push $W
  push $W
.endif
  $NEXT


$DEFCODE "OVER", 4, 0, OVER
  ; ( a b -- a b a )
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, sp[4]
.else
  pop $W
  pop $X
  push $X
  push $W
  push $X
.endif
  $NEXT


$DEFCODE "ROT", 3, 0, ROT
  ; ( a b c -- b c a )
.ifdef FORTH_TIR
  lw $W, sp[4]                         ; a
  lw $X, sp                            ; b
  stw sp[4], $X
  stw sp, $TOS
  mov $TOS, $W
.else
  pop $W
  pop $X
  pop $Y
  push $X
  push $W
  push $Y
.endif
  $NEXT


$DEFCODE "-ROT", 4, 0, NROT
  ; ( a b c -- c a b )
.ifdef FORTH_TIR
  lw $W, sp[4]                         ; a
  lw $X, sp                            ; b
  stw sp[4], $TOS
  stw sp, $W
  mov $TOS, $X
.else
  pop $W
  pop $X
  pop $Y
  push $W
  push $Y
  push $X
.endif
  $NEXT


$DEFCODE "2DROP", 5, 0, TWODROP
  ; ( n n -- )
.ifdef FORTH_TIR
  pop $TOS
  pop $TOS
.else
  pop $W
  pop $W
.endif
  $NEXT


$DEFCODE "2DUP", 4, 0, TWODUP
  ; ( a b -- a b a b )
.ifdef FORTH_TIR
  lw $W, sp
  push $TOS
  push $W
.else
  pop $W
  pop $X
  push $X
  push $W
  push $X
  push $W
.endif
  $NEXT


$DEFCODE "2SWAP", 5, 0, TWOSWAP
  ; ( a b c d -- c d a b )
.ifdef FORTH_TIR
  lw $W, sp[8] ; a
  lw $X, sp[4] ; b
  lw $Y, sp    ; c
  stw sp[8], $Y
  stw sp[4], $TOS
  stw sp,    $W
  mov $TOS, $X
.else
  pop $W
  pop $X
  pop $Y
  pop $Z
  push $X
  push $W
  push $Z
  push $Y
.endif
  $NEXT


;
; Input and output
;

$DEFCODE "CHAR", 4, 0, CHAR
  ; ( -- n )
  call &__read_dword_with_refill
  inc r0
.ifdef FORTH_TIR
  push $TOS
  lb $TOS, r0
.else
  lb $W, r0 ; load the first character of next word into W...
  push $W
.endif
  $NEXT


$DEFCODE "[CHAR]", 6, $F_IMMED, BRACKETCHAR
  call &__read_dword_with_refill
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
.ifdef FORTH_TIR
  $pushrsp $TOS
  pop $TOS
.else
  pop $W
  $pushrsp $W
.endif
  $NEXT


$DEFCODE "R>", 2, 0, FROMR
.ifdef FORTH_TIR
  push $TOS
  $poprsp $TOS
.else
  $poprsp $W
  push $W
.endif
  $NEXT


$DEFCODE "RSP@", 4, 0, RSPFETCH
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, $RSP
.else
  push $RSP
.endif
  $NEXT


$DEFCODE "RSP!", 4, 0, RSPSTORE
.ifdef FORTH_TIR
  mov $RSP, $TOS
  pop $TOS
.else
  pop $RSP
.endif
  $NEXT


$DEFCODE "RDROP", 5, 0, RDOP
  $poprsp $W
  $NEXT


$DEFCODE "R@", 2, 0, RFETCH
  ; ( -- x ) ( R:  x -- x )
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $RSP
.else
  lw $W, $RSP
  push $W
.endif
  $NEXT


;
; Parameter stack
;

$DEFCODE "DSP@", 4, 0, DSPFETCH
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, sp
.else
  push sp
.endif
  $NEXT


$DEFCODE "DSP!", 4, 0, DSPSTORE
.ifdef FORTH_TIR
  mov sp, $TOS
  pop $TOS
.else
  pop sp
.endif
  $NEXT


;
; Memory operations
;
$DEFCODE "!", 1, 0, STORE
  ; ( data address -- )
.ifdef FORTH_TIR
  pop $W
  stw $TOS, $W
  pop $TOS
.else
  pop $W
  pop $X
  stw $W, $X
.endif
  $NEXT


$DEFCODE "@", 1, 0, FETCH
  ; ( address -- n )
.ifdef FORTH_TIR
  lw $TOS, $TOS
.else
  pop $W
  lw $W, $W
  push $W
.endif
  $NEXT


$DEFCODE "+!", 2, 0, ADDSTORE
  ; ( amount address -- )
.ifdef FORTH_TIR
  pop $W
  lw $Y, $TOS
  add $Y, $W
  stw $TOS, $Y
  pop $TOS
.else
  pop $W
  pop $X
  lw $Y, $W
  add $Y, $X
  stw $W, $Y
.endif
  $NEXT


$DEFCODE "-!", 2, 0, SUBSTORE
  ; ( amount address -- )
.ifdef FORTH_TIR
  pop $W
  lw $Y, $TOS
  sub $Y, $W
  stw $TOS, $Y
  pop $TOS
.else
  pop $W
  pop $X
  lw $Y, $W
  sub $Y, $X
  stw $W, $Y
.endif
  $NEXT


$DEFCODE "C!", 2, 0, STOREBYTE
  ; ( data address -- )
.ifdef FORTH_TIR
  pop $W
  stb $TOS, $W
  pop $TOS
.else
  pop $W
  pop $X
  stb $W, $X
.endif
  $NEXT


$DEFCODE "C@", 2, 0, FETCHBYTE
  ; ( address -- n )
.ifdef FORTH_TIR
  lb $TOS, $TOS
.else
  pop $W
  lb $W, $W
  push $W
.endif
  $NEXT


;
; Strings
;

$DEFCODE "SQUOTE_LITSTRING", 9, 0, SQUOTE_LITSTRING
  ; ( -- c-addr u )
  lb $W, $FIP     ; load length
  inc $FIP        ; FIP points to string
.ifdef FORTH_TIR
  push $TOS
  push $FIP
  mov $TOS, $W
.else
  push $FIP       ; push string addr
  push $W         ; push string length
.endif
  add $FIP, $W    ; skip string
  $align4 $FIP    ; align FIP
  $NEXT


$DEFCODE "CQUOTE_LITSTRING", 9, 0, CQUOTE_LITSTRING
  ; ( -- c-addr )
.ifdef FORTH_TIR
  push $TOS
  mov $TOS, $FIP
.else
  push $FIP       ; push c-addr
.endif
  lb $W, $FIP     ; load string length
  inc $FIP        ; skip length
  add $FIP, $W    ; skip string
  $align4 $FIP    ; align FIP
  $NEXT


$DEFCODE "TELL", 4, 0, TELL
  ; ( c-addr u -- )
.ifdef FORTH_TIR
  pop r0
  mov r1, $TOS
  pop $TOS
.else
  pop r1
  pop r0
.endif
  call &write
  $NEXT


;
; Loop helpers
;

$DEFCODE "(DO)", 4, 0, PAREN_DO
  ; ( control index -- )
.ifdef FORTH_TIR
  pop $X
  $pushrsp $X
  $pushrsp $TOS
  pop $TOS
.else
  pop $W ; index
  pop $X ; control
  $pushrsp $X ; control
  $pushrsp $W ; index
.endif
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


$DEFCODE "(+LOOP)", 7, 0, PAREN_PLUS
  $poprsp $W ; index
  $poprsp $X ; control
  mov $Z, $W  ; save old index for later
.ifdef FORTH_TIR
  add $W, $TOS
  pop $TOS
.else
  pop $Y
  add $W, $Y
.endif
  sub $Z, $X  ; (index - limit)
  mov $Y, $W  ; (index + n)
  sub $Y, $X  ; (index - limit + n)
  xor $Z, $Y
  bs &__PARENPLUS_next
  $pushrsp $X
  $pushrsp $W
  lw $W, $FIP
  add $FIP, $W
  $NEXT
__PARENPLUS_next:
  add $FIP, $CELL
  $NEXT


$DEFCODE "UNLOOP", 6, 0, UNLOOP
  add $RSP, 8 ; CELL * 2
  $NEXT


$DEFCODE "I", 1, 0, I
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $RSP
.else
  lw $W, $RSP
  push $W
.endif
  $NEXT


$DEFCODE "J", 1, 0, J
.ifdef FORTH_TIR
  push $TOS
  lw $TOS, $RSP[8]
.else
  lw $W, $RSP[8]
  push $W
.endif
  $NEXT


$DEFDOESWORD "LEAVE-SP", 8, 0, LEAVE_SP
  .int 0x00000000
__LEAVE_SP_payload:
  .int &__LEAVE_SP_payload
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000
  .int 0x00000000


$DEFWORD "LEAVE", 5, $F_IMMED, LEAVE
  .int &BRACKET_TICK
  .int &UNLOOP
  .int &COMMA
  .int &BRACKET_TICK
  .int &BRANCH
  .int &COMMA
  .int &LEAVE_SP
  .int &FETCH
  .int &LEAVE_SP
  .int &SUB
  .int &LIT
  .int 0x0000001F
  .int &CELLS
  .int &GT
  .int &ZBRANCH
  .int 0x00000008
  .int &ABORT
  .int &LIT
  .int 0x00000001
  .int &CELLS
  .int &LEAVE_SP
  .int &ADDSTORE
  .int &HERE
  .int &LEAVE_SP
  .int &FETCH
  .int &STORE
  .int &LIT
  .int 0x00000000
  .int &COMMA
  .int &EXIT


$DEFWORD "RESOLVE-DO", 10, 0, RESOLVE_DO
  .int &ZBRANCH
  .int 0x00000044
  .int &DUP
  .int &HERE
  .int &SUB
  .int &COMMA
  .int &DUP
  .int &LIT
  .int 0x00000002
  .int &CELLS
  .int &SUB
  .int &HERE
  .int &OVER
  .int &SUB
  .int &SWAP
  .int &STORE
  .int &BRANCH
  .int 0x00000014
  .int &DUP
  .int &HERE
  .int &SUB
  .int &COMMA
  .int &EXIT


$DEFWORD "RESOLVE-LEAVES", 14, 0, RESOLVE_LEAVES
  .int &LEAVE_SP
  .int &FETCH
  .int &FETCH
  .int &OVER
  .int &GT
  .int &LEAVE_SP
  .int &FETCH
  .int &LEAVE_SP
  .int &GT
  .int &AND
  .int &ZBRANCH
  .int 0x00000048
  .int &HERE
  .int &LEAVE_SP
  .int &FETCH
  .int &FETCH
  .int &SUB
  .int &LEAVE_SP
  .int &FETCH
  .int &FETCH
  .int &STORE
  .int &LIT
  .int 0x00000001
  .int &CELLS
  .int &NEGATE
  .int &LEAVE_SP
  .int &ADDSTORE
  .int &BRANCH
  .int 0xFFFFFF90
  .int &DROP
  .int &EXIT


$DEFWORD "DO", 2, $F_IMMED, DO
  .int &BRACKET_TICK
  .int &PAREN_DO
  .int &COMMA
  .int &HERE
  .int &LIT
  .int 0x00000000
  .int &EXIT


$DEFWORD "?DO", 3, $F_IMMED, QUESTIONDO
  .int &BRACKET_TICK
  .int &TWODUP
  .int &COMMA
  .int &BRACKET_TICK
  .int &NEQU
  .int &COMMA
  .int &BRACKET_TICK
  .int &ZBRANCH
  .int &COMMA
  .int &LIT
  .int 0x00000000
  .int &COMMA
  .int &BRACKET_TICK
  .int &PAREN_DO
  .int &COMMA
  .int &HERE
  .int &LIT
  .int 0x00000001
  .int &EXIT


$DEFWORD "LOOP", 4, $F_IMMED, LOOP
  .int &BRACKET_TICK
  .int &PAREN_LOOP
  .int &COMMA
  .int &RESOLVE_DO
  .int &RESOLVE_LEAVES
  .int &EXIT


$DEFWORD "+LOOP", 5, $F_IMMED, PLUSLOOP
  .int &BRACKET_TICK
  .int &PAREN_PLUS
  .int &COMMA
  .int &RESOLVE_DO
  .int &RESOLVE_LEAVES
  .int &EXIT


;
; Constants
;
$DEFCODE "VERSION", 7, 0, VERSION
.ifdef FORTH_TIR
  push $TOS
  li $TOS, $DUCKY_VERSION
.else
  push $DUCKY_VERSION
.endif
  $NEXT


$DEFCODE "R0", 2, 0, RZ
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &rstack_top
  lw $TOS, $TOS
.else
  la $W, &rstack_top
  lw $W, $W
  push $W
.endif
  $NEXT


$DEFCODE "DOCOL", 5, 0, __DOCOL
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &DOCOL
.else
  la $W, &DOCOL
  push $W
.endif
  $NEXT


$DEFCODE "F_IMMED", 7, 0, __F_IMMED
.ifdef FORTH_TIR
  push $TOS
  li $TOS, $F_IMMED
.else
  push $F_IMMED
.endif
  $NEXT


$DEFCODE "F_HIDDEN", 8, 0, __F_HIDDEN
.ifdef FORTH_TIR
  push $TOS
  li $TOS, $F_HIDDEN
.else
  push $F_HIDDEN
.endif
  $NEXT


$DEFCODE "TRUE", 4, 0, TRUE
.ifdef FORTH_TIR
  push $TOS
  $load_true $TOS
.else
  $push_true $W
.endif
  $NEXT


$DEFCODE "FALSE", 5, 0, FALSE
.ifdef FORTH_TIR
  push $TOS
  $load_false $TOS
.else
  $push_false $W
.endif
  $NEXT


$DEFCODE "DODOES", 6, 0, __DODOES
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &DODOES
.else
  la $W, &DODOES
  push $W
.endif
  $NEXT


$DEFWORD "CONSTANT", 8, 0, CONSTANT
  .int &DWORD
  .int &HEADER_COMMA
  .int &__DOCOL
  .int &COMMA
  .int &BRACKET_TICK
  .int &LIT
  .int &COMMA
  .int &COMMA
  .int &BRACKET_TICK
  .int &EXIT
  .int &COMMA
  .int &EXIT


$DEFWORD "VARIABLE", 8, 0, VARIABLE
  .int &DWORD
  .int &HEADER_COMMA
  .int &__DODOES
  .int &COMMA
  .int &LIT
  .int 0
  .int &COMMA
  .int &LIT
  .int 1
  .int &CELLS
  .int &ALLOT
  .int &EXIT


$DEFWORD "CREATE", 6, 0, CREATE
  .int &DWORD
  .int &HEADER_COMMA
  .int &__DODOES
  .int &COMMA
  .int &LIT
  .int 0
  .int &COMMA
  .int &EXIT


$DEFWORD "DOES>", 5, 0, DOESTO
  .int &FROMR
  .int &LATEST
  .int &FETCH
  .int &TDFA
  .int &STORE
  .int &EXIT


$DEFWORD "VALUE", 5, 0, VALUE
  .int &DWORD
  .int &HEADER_COMMA
  .int &__DOCOL
  .int &COMMA
  .int &BRACKET_TICK
  .int &LIT
  .int &COMMA
  .int &COMMA
  .int &BRACKET_TICK
  .int &EXIT
  .int &COMMA
  .int &EXIT


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


$DEFCODE "CRASH", 5, $F_IMMED, CRASH
  hlt 0x4FFF


$DEFCODE "DIE", 3, 0, DIE
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
