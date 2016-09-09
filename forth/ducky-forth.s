; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "ducky-forth-defs.s"
.include "arch/control.hs"
.include "arch/keyboard.hs"
.include "arch/rtc.hs"
.include "arch/boot.hs"
.include "arch/tty.hs"
.include "arch/hdt.hs"


.macro TTY_LOAD reg:
  la #reg, &tty_mmio_address
  lw #reg, #reg
.end

  ; These symbols mark starting addreses of their sections - necessary for
  ; relocation of sections
  .data
  .type __data_boundary_start, int
  .int 0xDEADBEEF

  .section .rodata
  .type __rodata_boundary_start, int
  .int 0xDEADBEEF


  .section .text.boot, rxl

  ; This is where bootloader jump to, main entry point
_entry:
  ; Stop all secondary cores, this FORTH kernel has no use for SMP
  ctr r0, $CONTROL_CPUID
  bz &boot_phase1
  hlt 0xFFFF


  .text

__text_boundary_start:
  ret

;
; void __idle(void)
;
; Enter an "idle" mode, and wait for current CPU to be woken up
; by exception request.
;
  .global __idle

__idle:
  idle
  ret

__vmdebug_on:
  push r0
  ctr r0, $CONTROL_FLAGS
  or r0, $CONTROL_FLAG_VMDEBUG
  ctw $CONTROL_FLAGS, r0
  pop r0
  ret

__vmdebug_off:
  push r0
  push r1
  ctr r0, $CONTROL_FLAGS
  li r1, $CONTROL_FLAG_VMDEBUG
  not r1
  and r0, r1
  ctw $CONTROL_FLAGS, r0
  pop r1
  pop r0
  ret

  ; Welcome and bye messages
  .section .rodata

  .type __build_stamp_length, byte
  .byte 57

  .type __build_stamp, string
  .string "$BUILD_STAMP"


  .text


;
; void halt(u32_t exit_code)
;
  .global halt
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
  $align4 r2

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
; Unfortunatelly, there are some obstackles in the way - EVT, HDT, CWT, maybe
; even some mmaped IO ports, ... EVT and HDT can be moved, devices can be
; convinced to move ports to differet offsets, but CWT is bad - if we want to
; use more than one CPU core... Which we don't want to \o/
__relocate_sections:
  la r0, &__text_boundary_start
  la r1, &__text_boundary_end
  call &__relocate_section

  la r0, &__rodata_boundary_start
  la r1, &__rodata_boundary_end
  call &__relocate_section

  la r0, &__data_boundary_start
  la r1, &__data_boundary_end
  call &__relocate_section

  li r0, $USERSPACE_BASE
  li r1, $BOOT_LOADER_ADDRESS
  add r0, r1
  mov r1, r0
  add r1, $USERSPACE_SIZE
  call &__relocate_section

  ; No other sections needs to be relocated - yet. C code may
  ; produce some sections as well, but as long as such code is not
  ; being called after boot phase #1 is jumped to, it is not necessary
  ; to move its sections. And so far I intend to use C only for
  ; parsing HDT, and that happens in boot phase #1. We're safe.
  ret


;
; void boot_phase1(void) __attribute__((noreturn))
;
; This is the first phase of kernel booting process. Its main goal is to
; relocate kernel sections to the beggining of the address space.
;
boot_phase1:
  ; First, setup our boot stack.
  la sp, &.bootstack
  add sp, $PAGE_SIZE

  ; Next, turn of debugging.
  ;call &__vmdebug_off

  ; There's nothing blocking us from relocating our sections to more convenient
  ; place since the .text section should start at 0xA00, at least, leaving
  ; enough space for HDT.
  call &__relocate_sections

  ; Do long jump to new, relocated version of boot_phase2
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
  ; Re-set boot stack to use the correct, relocated address
  la sp, .bootstack
  add sp, $PAGE_SIZE

  ; Set LATEST to the correct value, after relocation
  la r0, &var_LATEST
  la r1, &name_BYE
  stw r0, r1

  ; Call the C code - that will do biggest part of necessary work
  call do_boot_phase2

  ; Get rid of boot stack
  la r0, var_SZ
  lw sp, r0

  ; Init TOS
  li $TOS, 0xBEEF
  liu $TOS, 0xDEAD

  ; Return stack
  la r0, rstack_top
  lw $RSP, r0

  ; Tell CPU about or EVT
  la r0, var_EVT
  lw r0, r0
  ctw $CONTROL_EVT, r0

  ; init pictured numeric output buffer
  call &__reset_pno_buffer

  ; Invalidate all CPU caches
  fptc

  ; give up the privileged mode
  ; lpm

  ; Enable interrupts as well
  sti

  ; And boot the FORTH itself...
  la $FIP, &cold_start
  $NEXT


;
; void nop_esr(void)
;
; NOP ISR - just retint, we have nothing else to do.
;
nop_esr:
  retint

  .global nop_esr


;
; void rtc_isr(void)
;
; RTC interrupt service routine.
;
rtc_esr:
  retint

  .global rtc_esr


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
  mov $FIP, $Z

__DODOES_push:
  add $W, $CELL           ; W points to Param Field #1 - payload address
  push $TOS
  mov $TOS, $W
  $NEXT


  .section .rodata
  .align 4
cold_start:
  .int &WELCOME
  .int &QUIT


  .data

  .align 4
  .global rstack_top
  .type rstack_top, int
  .int 0xFFFFFE00

  .type jiffies, int
  .int 0x00000000

  ; Memory-related info - where do interesting things start?
  .global memory_size
  .type memory_size, int
  .int 0x01000000

  .global __mm_evt
  .type __mm_evt, int
  .int 0xFFFFFFFF

  .global __mm_heap
  .type __mm_heap, int
  .int 0xDEADBEEF

  .global __mm_rtc_esr_sp
  .type __mm_rtc_esr_sp, int
  .int 0xDEADBEEF

  .global __mm_kbd_esr_sp
  .type __mm_kbd_esr_sp, int
  .int 0xDEADBEEF

  .global __mm_failsafe_esr_sp
  .type __mm_failsafe_esr_sp, int
  .int 0xDEADBEEF

  .global __mm_rsp
  .type __mm_rsp, int
  .int 0xDEADBEEF

  .global __mm_sp
  .type __mm_sp, int
  .int 0xDEADBEEF


  ; Temporary stack
  ; Keep it in a separate section, so it can be BSS, and reused when not needed anymore
  .section .bootstack, rwbl
  .space $PAGE_SIZE

  ; User data area
  ; Keep it in separate section to keep it aligned, clean, unpoluted
  .section .userspace, rwbl
  .space $USERSPACE_SIZE


  ; Welcome ducky
  .section .rodata

  .type __ducky_welcome, string
  .string "\r\n\n                     ____             _          _____ ___  ____ _____ _   _ \r\n          \033[93m__\033[0m        |  _ \ _   _  ___| | ___   _|  ___/ _ \|  _ \_   _| | | |\r\n        \033[31m<\033[0m\033[93m(o )___\033[0m    | | | | | | |/ __| |/ / | | | |_ | | | | |_) || | | |_| |\r\n         \033[93m( ._> /\033[0m    | |_| | |_| | (__|   <| |_| |  _|| |_| |  _ < | | |  _  |\r\n          \033[93m`---'\033[0m     |____/ \__,_|\___|_|\_\\\\__, |_|   \___/|_| \_\|_| |_| |_|\r\n                                           |___/                             \r\n\n\n"


  .set %link, 0

;
; Variables
;
$DEFVAR "EVT", 3, 0, EVT, 0x00000000
$DEFVAR "TEST-MODE", 9, 0, TEST_MODE, 0x00000000
$DEFVAR "ECHO", 4, 0, ECHO, 0
$DEFVAR "UP", 2, 0, UP, $USERSPACE_BASE
$DEFVAR "STATE", 5, 0, STATE, 0
$DEFVAR "DP", 2, 0, DP, $USERSPACE_BASE
$DEFVAR "LATEST", 6, 0, LATEST, &name_BYE
$DEFVAR "S0", 2, 0, SZ, 0xFFFFFF00
$DEFVAR "BASE", 4, 0, BASE, 10
$DEFVAR "SHOW-PROMPT", 11, 0, SHOW_PROMPT, 0


$DEFCODE "DUCKY", 5, $F_HIDDEN, DUCKY
  la r0, &__ducky_welcome
  call putcs
  $NEXT



$DEFWORD "WELCOME", 7, 0, WELCOME
  .int &TEST_MODE
  .int &FETCH
  .int &NOT
  .int &ZBRANCH
  .int 0x000000A8
  .int &DUCKY
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
  .int &SQUOTE_LITSTRING
  .int 0x70795413
  .int 0x42222065
  .int 0x20224559
  .int 0x65206F74
  .int 0x20746978
  .int &TELL
  .int &CR
  .int &TRUE
  .int &SHOW_PROMPT
  .int &STORE
  .int &TRUE
  .int &ECHO
  .int &STORE
  .int &VMDEBUGON
  .int &EXIT


$DEFCODE "BUILD-STAMP", 11, 0, BUILD_STAMP
  ; ( -- addr u )
  push $TOS
  la $X, &__build_stamp_length
  lb $TOS, $X
  inc $X
  push $X
  $NEXT


$DEFCODE "VMDEBUGON", 9, $F_IMMED, VMDEBUGON
  ; ( -- )
  call &__vmdebug_on
  $NEXT


$DEFCODE "VMDEBUGOFF", 10, $F_IMMED, VMDEBUGOFF
  call &__vmdebug_off
  $NEXT


$DEFCODE "PROMPT", 6, 0, PROMPT
  ; ( flag -- )
  mov r0, $TOS
  pop $TOS
  call print_prompt
  $NEXT


;****************************
;
; Terminal IO routines and words
;
;****************************

  .data

  ; word_buffer lies right next to word_buffer_length, pretending it's
  ; a standard counted string <length><chars...>
  .global word_buffer_length
  .type word_buffer_length, byte
  .byte 0

  .global word_buffer
  .type word_buffer, space
  .space $WORD_BUFFER_SIZE

  .align 4

  .global kbd_mmio_address
  .type kbd_mmio_address, int
  .int 0xFAFAFAFA

  .global tty_mmio_address
  .type tty_mmio_address, int
  .int 0xFBFBFBFB

  .global rtc_mmio_address
  .type rtc_mmio_address, int
  .int 0xFCFCFCFC


$DEFCODE "WORD", 4, 0, WORD
  ; ( char "<chars>ccc<char>" -- c-addr )
  mov r0, $TOS
  call &__read_word_with_refill
  mov $TOS, r0
  $NEXT


$DEFCODE "DWORD", 5, 0, DWORD
  ; ( "<chars>ccc<char>" -- c-addr )
  ; like WORD but with space as a delimiter ("default WORD")
  call &__read_dword_with_refill
  push $TOS
  mov $TOS, r0
  $NEXT


;
; PARSE
;

; f_parse_result_t instance
  .data
__PARSE_result:
  .int 0x00000000  ; pr_word = NULL
  .int 0x00000000  ; pr_length = NULL

$DEFCODE "PARSE", 5, 0, PARSE
  ; ( char "ccc<char>" -- c-addr u )
  ;
  ; Parse ccc delimited by the delimiter char.
  ; c-addr is the address (within the input buffer) and u is the length
  ; of the parsed string. If the parse area was empty, the resulting string
  ; has a zero length.

  la $W, __PARSE_result

  mov r0, $TOS
  mov r1, $W
  call do_PARSE

  ; push pr_word
  lw $X, $W
  push $X
  ; push pr_length
  lw $TOS, $W[$WORD_SIZE]
  $NEXT


$DEFCODE "ACCEPT", 6, 0, ACCEPT
  ; ( c-addr +n1 -- +n2 )
  mov r1, $TOS
  pop r0
  call __read_line_from_kbd
  mov $TOS, r0
  $NEXT


$DEFCODE "REFILL", 6, 0, REFILL
  ; ( -- flag )
  call __refill_input_buffer
  push $TOS
  $load_true $TOS
  $NEXT


$DEFCODE "KEY", 3, 0, KEY
  ; ( -- n )
  call __read_char
  push $TOS
  mov $TOS, r0
  $NEXT


$DEFCODE "EMIT", 4, 0, EMIT
  ; ( n -- )
  mov r0, $TOS
  pop $TOS
  call putc
  $NEXT


$DEFCODE "EVALUATE", 8, 0, EVALUATE
  ; ( i*x c-addr u -- j*x )
  ;
  ; Save the current input source specification. Store minus-one (-1)
  ; in SOURCE-ID if it is present. Make the string described by c-addr
  ; and u both the input source and input buffer, set >IN to zero, and
  ; interpret. When the parse area is empty, restore the prior input
  ; source specification. Other stack effects are due to the words EVALUATEd.
  mov r1, $TOS
  pop r0
  pop $TOS
  call do_EVALUATE
  $NEXT


$DEFCODE ">IN", 3, 0, TOIN
  ; ( -- a-addr )
  call do_TOIN
  push $TOS
  mov $TOS, r0
  $NEXT


$DEFCODE "TYPE", 4, 0, TYPE
  ; ( address length -- )
  mov r1, $TOS
  pop r0
  pop $TOS
  call puts
  $NEXT


$DEFCODE "SOURCE-ID", 9, 0, SOURCE_ID
  la $W, current_input
  push $TOS
  lw $TOS, $W
  $NEXT


$DEFCODE "SOURCE", 6, 0, SOURCE
  ; ( -- address length )
  ;
  ; c-addr is the address of, and u is the number of characters in,
  ; the input buffer.
  la $W, current_input
  lw $W, $W
  lw $X, $W[8]
  lw $Y, $W[12]

  push $TOS
  lw $TOS, $W[8]
  push $TOS
  lw $TOS, $W[12]
  $NEXT


  .data

  .type __found_word, int
  .int 0x00000000

$DEFCODE "FIND", 4, 0, FIND
  ; ( c-addr -- c-addr 0 | xt 1 | xt -1 )
  mov $X, $TOS                         ; save c-addr for later
  mov r0, $TOS
  inc r0
  mov r1, $TOS
  lb r1, r1
  la r2, __found_word
  call fw_search
  cmp r0, 0
  bz &__FIND_notfound
  push r0 ; save find's result for later
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  pop r1
  push r0
  mov $TOS, r1
  j &__FIND_next
__FIND_notfound:
  push $X                              ; saved c-addr
  li $TOS, 0x00
__FIND_next:
  $NEXT


$DEFCODE "'", 1, $F_IMMED, TICK
  ; ( "<spaces>name" -- xt )
  call __read_dword_with_refill
  $unpack_word_for_find
  la r2, __found_word
  call fw_search
  cmp r0, 0
  bz __ERR_undefined_word
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  push $TOS
  mov $TOS, r0
  $NEXT


$DEFCODE "[']", 3, 0, BRACKET_TICK
  push $TOS
  lw $TOS, $FIP
  add $FIP, $CELL
  $NEXT


$DEFCODE ">CFA", 4, 0, TCFA
  ; ( address -- address )
  mov r0, $TOS
  call do_TCFA
  mov $TOS, r0
  $NEXT


$DEFWORD ">DFA", 4, 0, TDFA
  .int &TCFA
  .int &LIT
  .int $CELL
  .int &ADD
  .int &EXIT


$DEFCODE "EXECUTE", 7, 0, EXECUTE
  mov $W, $TOS
  pop $TOS
  lw $X, $W
  j $X


$DEFCODE "LIT", 3, 0, LIT
  push $TOS
  lw $TOS, $FIP
  add $FIP, $CELL
  $NEXT


$DEFCODE "HEADER,", 7, 0, HEADER_COMMA
  ; ( c-addr -- )
  mov r0, $TOS
  inc r0
  mov r1, $TOS
  lb r1, r1
  pop $TOS
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
  mov r0, $TOS
  pop $TOS
  call do_COMMA
  $NEXT


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
  add $TOS, $wr_flags
  lb $X, $TOS
  xor $X, $F_HIDDEN
  stb $TOS, $X
  pop $TOS
  $NEXT


$DEFCODE "BRANCH", 6, 0, BRANCH
  ; ( -- )
  lw $W, $FIP
  add $FIP, $W
  $NEXT


$DEFCODE "0BRANCH", 7, 0, ZBRANCH
  ; ( n -- )
  mov $W, $TOS
  pop $TOS
  cmp $W, $W
  bz &code_BRANCH
  add $FIP, $CELL
  $NEXT


  .data
__interpret_decision:
  .int 0x00000000
  .int 0x00000000


$DEFCODE "INTERPRET", 9, 0, INTERPRET
  la r0, __interpret_decision
  call do_INTERPRET

  la r0, __interpret_decision
  lw r1, r0
  bz __INTERPRET_next

  cmp r1, 0x01
  be __INTERPRET_execute_word

  cmp r1, 0x02
  be __INTERPRET_execute_lit

  j __ERR_interpret_fail

__INTERPRET_execute_word:
  la r0, __interpret_decision
  lw $W, r0[$WORD_SIZE]
  lw $X, $W
  j $X

__INTERPRET_execute_lit:
  lw r1, r0[$CELL]
  push $TOS
  mov $TOS, r1
__INTERPRET_next:
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
  $load_true $TOS
  $NEXT

__CMP_false:
  $load_false $TOS
  $NEXT


$DEFCODE "=", 1, 0, EQU
  ; ( a b -- n )
  pop $W
  cmp $W, $TOS
  $TF_FINISH EQU, be


$DEFCODE "<>", 2, 0, NEQU
  ; ( a b -- n )
  pop $W
  cmp $W, $TOS
  $TF_FINISH NEQU, bne


$DEFCODE "0=", 2, 0, ZEQU
  ; ( n -- n )
  cmp $TOS, 0
  $TF_FINISH ZEQU, bz


$DEFCODE "0<>", 3, 0, ZNEQU
  ; ( n -- n )
  cmp $TOS, 0
  $TF_FINISH ZNEQU, bnz


$DEFCODE "<", 1, 0, LT
  ; ( a b -- n )
  pop $W
  cmp $W, $TOS
  $TF_FINISH LT, bl


$DEFCODE ">", 1, 0, GT
  pop $W
  cmp $W, $TOS
  $TF_FINISH GT, bg


$DEFCODE "<=", 2, 0, LE
  pop $W
  cmp $W, $TOS
  $TF_FINISH LE, ble


$DEFCODE ">=", 2, 0, GE
  pop $W
  cmp $W, $TOS
  $TF_FINISH GE, bge


$DEFCODE "0<", 2, 0, ZLT
  ; ( n -- flag )
  ; flag is true if and only if n is less than zero
  cmp $TOS, 0
  $TF_FINISH ZLT, bl


$DEFCODE "0>", 2, 0, ZGT
  ; ( n -- flag )
  ; flag is true if and only if n is greater than zero
  cmp $TOS, 0
  $TF_FINISH ZGT, bg


$DEFCODE "0<=", 3, 0, ZLE
  cmp $TOS, 0
  $TF_FINISH ZLE, ble


$DEFCODE "0>=", 3, 0, ZGE
  cmp $TOS, 0
  $TF_FINISH ZGE, bge


$DEFCODE "?DUP", 4, 0, QDUP
  cmp $TOS, 0
  bnz &__QDUP_nonzero
  li $TOS, 0x00
  $NEXT
__QDUP_nonzero:
  push $TOS
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
  ; ( a b -- <a / b> )
  pop $W
  div $W, $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "MOD", 3, 0, MOD
  ; ( a b -- <a % b> )
  pop $W
  mod $W, $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "/MOD", 4, 0, DIVMOD
  ; ( a b -- <a % b> <a / b> )
  pop $W
  mov $X, $W
  div $W, $TOS
  mod $X, $TOS
  push $X
  mov $TOS, $W
  $NEXT


$DEFCODE "AND", 3, 0, AND
  ; ( x1 x2 -- <x1 & x2> )
  pop $W
  and $TOS, $W
  $NEXT


$DEFCODE "OR", 2, 0, OR
  pop $W
  or $TOS, $W
  $NEXT


$DEFCODE "XOR", 3, 0, XOR
  pop $W
  xor $TOS, $W
  $NEXT


$DEFCODE "INVERT", 6, 0, INVERT
  not $TOS
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
  ; ( a -- a a )
  push $TOS
  $NEXT


$DEFCODE "OVER", 4, 0, OVER
  ; ( a b -- a b a )
  push $TOS
  lw $TOS, sp[$CELL]
  $NEXT


$DEFCODE "ROT", 3, 0, ROT
  ; ( a b c -- b c a )
  lw $W, sp[4]                         ; a
  lw $X, sp                            ; b
  stw sp[4], $X
  stw sp, $TOS
  mov $TOS, $W
  $NEXT


$DEFCODE "-ROT", 4, 0, NROT
  ; ( a b c -- c a b )
  lw $W, sp[4]                         ; a
  lw $X, sp                            ; b
  stw sp[4], $TOS
  stw sp, $W
  mov $TOS, $X
  $NEXT


$DEFCODE "2DROP", 5, 0, TWODROP
  ; ( n n -- )
  pop $TOS
  pop $TOS
  $NEXT


$DEFCODE "2DUP", 4, 0, TWODUP
  ; ( a b -- a b a b )
  lw $W, sp
  push $TOS
  push $W
  $NEXT


$DEFCODE "2SWAP", 5, 0, TWOSWAP
  ; ( a b c d -- c d a b )
  lw $W, sp[8] ; a
  lw $X, sp[4] ; b
  lw $Y, sp    ; c
  stw sp[8], $Y
  stw sp[4], $TOS
  stw sp,    $W
  mov $TOS, $X
  $NEXT


;
; Input and output
;

$DEFCODE "CHAR", 4, 0, CHAR
  ; ( -- n )
  call &__read_dword_with_refill
  inc r0
  push $TOS
  lb $TOS, r0
  $NEXT


$DEFCODE "[CHAR]", 6, $F_IMMED, BRACKETCHAR
  call &__read_dword_with_refill
  inc r0
  lb $W, r0
  la r0, &LIT
  call do_COMMA
  mov r0, $W
  call do_COMMA
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


$DEFCODE "R@", 2, 0, RFETCH
  ; ( -- x ) ( R:  x -- x )
  push $TOS
  lw $TOS, $RSP
  $NEXT


;
; Parameter stack
;

$DEFCODE "DSP@", 4, 0, DSPFETCH
  push $TOS
  mov $TOS, sp
  $NEXT


$DEFCODE "DSP!", 4, 0, DSPSTORE
  mov sp, $TOS
  pop $TOS
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
  lw $Y, $TOS
  add $Y, $W
  stw $TOS, $Y
  pop $TOS
  $NEXT


$DEFCODE "-!", 2, 0, SUBSTORE
  ; ( amount address -- )
  pop $W
  lw $Y, $TOS
  sub $Y, $W
  stw $TOS, $Y
  pop $TOS
  $NEXT


$DEFCODE "C!", 2, 0, STOREBYTE
  ; ( data address -- )
  pop $W
  stb $TOS, $W
  pop $TOS
  $NEXT


$DEFCODE "C@", 2, 0, FETCHBYTE
  ; ( address -- n )
  lb $TOS, $TOS
  $NEXT


;
; Strings
;

$DEFCODE "SQUOTE_LITSTRING", 9, 0, SQUOTE_LITSTRING
  ; ( -- c-addr u )
  lb $W, $FIP     ; load length
  inc $FIP        ; FIP points to string
  push $TOS
  push $FIP
  mov $TOS, $W
  add $FIP, $W    ; skip string
  $align4 $FIP    ; align FIP
  $NEXT


$DEFCODE "CQUOTE_LITSTRING", 9, 0, CQUOTE_LITSTRING
  ; ( -- c-addr )
  push $TOS
  mov $TOS, $FIP
  lb $W, $FIP     ; load string length
  inc $FIP        ; skip length
  add $FIP, $W    ; skip string
  $align4 $FIP    ; align FIP
  $NEXT


$DEFCODE "TELL", 4, 0, TELL
  ; ( c-addr u -- )
  pop r0
  mov r1, $TOS
  pop $TOS
  call puts
  $NEXT


;
; Loop helpers
;

$DEFCODE "(DO)", 4, 0, PAREN_DO
  ; ( control index -- )
  pop $X
  $pushrsp $X
  $pushrsp $TOS
  pop $TOS
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
  add $W, $TOS
  pop $TOS
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
  push $TOS
  lw $TOS, $RSP
  $NEXT


$DEFCODE "J", 1, 0, J
  push $TOS
  lw $TOS, $RSP[8]
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
  push $TOS
  li $TOS, $DUCKY_VERSION
  $NEXT


$DEFCODE "R0", 2, 0, RZ
  push $TOS
  la $TOS, &rstack_top
  lw $TOS, $TOS
  $NEXT


$DEFCODE "DOCOL", 5, 0, __DOCOL
  push $TOS
  la $TOS, &DOCOL
  $NEXT


$DEFCODE "F_IMMED", 7, 0, __F_IMMED
  push $TOS
  li $TOS, $F_IMMED
  $NEXT


$DEFCODE "F_HIDDEN", 8, 0, __F_HIDDEN
  push $TOS
  li $TOS, $F_HIDDEN
  $NEXT


$DEFCODE "TRUE", 4, 0, TRUE
  push $TOS
  $load_true $TOS
  $NEXT


$DEFCODE "FALSE", 5, 0, FALSE
  push $TOS
  $load_false $TOS
  $NEXT


$DEFCODE "DODOES", 6, 0, __DODOES
  push $TOS
  la $TOS, &DODOES
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


$DEFCODE "TO", 2, $F_IMMED, TO
  call &__read_dword_with_refill
  $unpack_word_for_find
  la r2, __found_word
  call fw_search
  cmp r0, 0
  bz __ERR_undefined_word
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  add r0, $CELL                        ; point to Data Field
  add r0, $CELL                        ; point to value field

  la $W, &var_STATE
  lw $W, $W
  bz &__TO_store

  la $W, &var_DP
  lw $X, $W

  la $Z, &LIT
  stw $X, $Z
  add $X, $CELL

  stw $X, r0
  add $X, $CELL

  la $Z, &STORE
  stw $X, $Z
  add $X, $CELL

  stw $W, $X
  j &__TO_quit

__TO_store:
  stw r0, $TOS
  pop $TOS
__TO_quit:
  $NEXT


; Include non-kernel words
 .include "ducky-forth-words.s"
 .include "words/double-cell-ints.s"


$DEFCODE "\\\\", 1, $F_IMMED, BACKSLASH
  call flush_input_buffer
  $NEXT


$DEFCODE "HERE", 4, 0, HERE
  push $TOS
  la $TOS, &var_DP
  lw $TOS, $TOS
  $NEXT


$DEFCODE "CRASH", 5, 0, CRASH
  hlt 0x4FFF

$DEFCODE "CRASH-NOW", 9, $F_IMMED, CRASH_NOW
  hlt 0x4FFF


;
; The last command - if it's not the last one, modify initial value of LATEST
;
$DEFCSTUB "BYE", 3, 0, BYE
