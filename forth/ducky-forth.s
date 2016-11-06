/*
 * A minimal FORTH kernel for Ducky virtual machine
 *
 * This was written as an example and for educating myself, no higher ambitions intended.
 *
 * Heavily based on absolutely amazing FORTH tutorial by
 * Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
 */

#include <arch/control.h>
#include <arch/keyboard.h>
#include <arch/rtc.h>
#include <arch/boot.h>
#include <arch/tty.h>
#include <arch/hdt.h>

#include "forth.h"


  // These symbols mark starting addreses of their sections - necessary for
  // relocation of sections
  .data
  WORD(__data_boundary_start, 0xDEADBEEF)

  .section .rodata
  WORD(__rodata_boundary_start, 0xDEADBEEF)


  .section .text.boot, "rxl"

  // This is where bootloader jump to, main entry point
_entry:
  // Stop all secondary cores, this FORTH kernel has no use for SMP
  ctr r0, CONTROL_CPUID
  bz boot_phase1
  hlt 0xFFFF


  // Init link variable to NULL
  .set link, 0x00


  .text

__text_boundary_start:
  ret

/*
 * void __idle(void)
 *
 * Enter an "idle" mode, and wait for current CPU to be woken up
 * by exception request.
 */
  .global __idle

__idle:
  idle
  ret

__vmdebug_on:
  push r0
  ctr r0, CONTROL_FLAGS
  or r0, CONTROL_FLAG_VMDEBUG
  ctw CONTROL_FLAGS, r0
  pop r0
  ret

__vmdebug_off:
  push r0
  push r1
  ctr r0, CONTROL_FLAGS
  li r1, CONTROL_FLAG_VMDEBUG
  not r1
  and r0, r1
  ctw CONTROL_FLAGS, r0
  pop r1
  pop r0
  ret

  // Welcome and bye messages
  .section .rodata

  .type __build_stamp_length, byte, 57
  .type __build_stamp, string, XSTR(__BUILD_STAMP__)


  .text


//
// void halt(u32_t exit_code)
//
  .global halt
halt:
  hlt r0


//
// void memcpy(void *src, void *dst, u32_t length)
//
// Copy content of memory at SRC, of length of LENGTH bytes, to address DST.
// Source and destination areas should not overlap, otherwise memcpy could
// lead to unpredicted results.
//
memcpy:
  cmp r2, 0x00
  bz __memcpy_quit
  push r3
__memcpy_loop:
  lb r3, r0
  stb r1, r3
  inc r0
  inc r1
  dec r2
  bnz __memcpy_loop
  pop r3
__memcpy_quit:
  ret


//
// void memcpy4(void *src, void *dst, u32_t length)
//
// Copy content of memory at SRC, of length of LENGTH bytes, to address DST.
// Length of area must be multiply of 4. Source and destination areas should
// not overlap, otherwise memcpy could lead to unpredicted results.
//
memcpy4:
  cmp r2, 0x00
  bz __memcpy4_quit
  push r3
__memcpy4_loop:
  lw r3, r0
  stw r1, r3
  add r0, 4
  add r1, 4
  sub r2, 4
  bnz __memcpy4_loop
  pop r3
__memcpy4_quit:
  ret


//
// void __relocate_section(u32_t *first, u32_t *last)
//
__relocate_section:
  // we're moving section to the beggining of the address space,
  // basically subtracting BOOT_LOADER_ADDRESS from its start
  li r10, BOOT_LOADER_ADDRESS
  mov r2, r1

  // construct arguments for memcpy4
  // src: first, no change necessary
  // length: last - first
  sub r2, r0
  ALIGN_CELL(r2)

  // dst: start - BOOT_LOADER_ADDRESS
  mov r1, r0
  sub r1, r10

  call memcpy4

  ret


//
// void __relocate_sections(void)
//
// FORTH image is loaded by bootloader to address BOOT_LOADER_ADDRESS. This is
// unfortunate because - thanks to way how threaded code is implemented here -
// this offset breaks all absolute, compile-time references, hardcoded into
// links between words. Most of the other code would not care about running
// with a different base address but this breaks. I can't find other way how
// to deal with this, therefore the first think kernel does is relocating
// itself to the beggining of the address space.
//
// Unfortunatelly, there are some obstackles in the way - EVT, HDT, CWT, maybe
// even some mmaped IO ports, ... EVT and HDT can be moved, devices can be
// convinced to move ports to differet offsets, but CWT is bad - if we want to
// use more than one CPU core... Which we don't want to \o/
__relocate_sections:
  la r0, __text_boundary_start
  la r1, __text_boundary_end
  call __relocate_section

  la r0, __rodata_boundary_start
  la r1, __rodata_boundary_end
  call __relocate_section

  la r0, __data_boundary_start
  la r1, __data_boundary_end
  call __relocate_section

  ret


//
// void boot_phase1(void) __attribute__((noreturn))
//
// This is the first phase of kernel booting process. Its main goal is to
// relocate kernel sections to the beggining of the address space.
//
boot_phase1:
  // First, setup our boot stack.
  la sp, .bootstack
  add sp, PAGE_SIZE

  // Next, turn of debugging.
  call __vmdebug_off

  // There's nothing blocking us from relocating our sections to more convenient
  // place since the .text section should start at 0xA00, at least, leaving
  // enough space for HDT.
  call __relocate_sections

  // Do long jump to new, relocated version of boot_phase2
  la r0, boot_phase2
  li r1, BOOT_LOADER_ADDRESS
  sub r0, r1
  j r0


//
// void boot_phase2(void) __attribute__((noreturn))
//
// This is the second phase of kernel booting process. It does the rest of
// necessary work before handing over to FORTH words.
//
boot_phase2:
  // Re-set boot stack to use the correct, relocated address
  la sp, .bootstack
  add sp, PAGE_SIZE

  // Set LATEST to the correct value, after relocation
  la r0, var_LATEST
  la r1, name_BYE
  stw r0, r1

  // Call the C code - that will do biggest part of necessary work
  call do_boot_phase2

  // Get rid of boot stack
  la r0, var_SZ
  lw sp, r0

  // Init TOS
  li TOS, 0xBEEF
  liu TOS, 0xDEAD

  // Return stack
  la r0, rstack_top
  lw RSP, r0

  // Tell CPU about or EVT
  la r0, var_EVT
  lw r0, r0
  ctw CONTROL_EVT, r0

  // init pictured numeric output buffer
  call pno_reset_buffer

  // Invalidate all CPU caches
  fptc

  // give up the privileged mode
  // lpm

  // Enable interrupts as well
  sti

  // And boot the FORTH itself...
  la FIP, cold_start
  NEXT


//
// void nop_esr(void)
//
// NOP ISR - just retint, we have nothing else to do.
//
nop_esr:
  retint

  .global nop_esr


//
// void rtc_isr(void)
//
// RTC interrupt service routine.
//
rtc_esr:
  retint

  .global rtc_esr


DOCOL:
  PUSHRSP(FIP)
  add W, CELL
  mov FIP, W
  NEXT


DODOES:
  // DODES is entered in the very same way as DOCOL:
  // X = address of Code Field routine, i.e. DODES
  // W = address of Code Field of this word
  //
  // Therefore:
  // *W       = CF
  // *(W + CELL) = address of behavior words
  // *(W + 2 * CELL) = address of this word's data

  add W, CELL           // W points to Param Field #0 - behavior cell
  lw Z, W
  bz __DODOES_push

  PUSHRSP(FIP)
  mov FIP, Z

__DODOES_push:
  add W, CELL           // W points to Param Field #1 - payload address
  push TOS
  mov TOS, W
  NEXT


  .section .rodata
  .align 4
cold_start:
  .word WELCOME
  .word QUIT


  .data

  WORD(rstack_top, 0xFFFFFE00)
  WORD(jiffies, 0x00000000)

  // Temporary stack
  // Keep it in a separate section, so it can be BSS, and reused when not needed anymore
  .section .bootstack, "rwbl"
  .space PAGE_SIZE

  // User data area
  // Keep it in separate section to keep it aligned, clean, unpoluted
  .section .userspace, "rwbl"
  .space CELL


  // Welcome ducky
  .section .rodata

  .type __ducky_welcome, string, "\r\n\n                     ____             _          _____ ___  ____ _____ _   _ \r\n          \033[93m__\033[0m        |  _ \ _   _  ___| | ___   _|  ___/ _ \|  _ \_   _| | | |\r\n        \033[31m<\033[0m\033[93m(o )___\033[0m    | | | | | | |/ __| |/ / | | | |_ | | | | |_) || | | |_| |\r\n         \033[93m( ._> /\033[0m    | |_| | |_| | (__|   <| |_| |  _|| |_| |  _ < | | |  _  |\r\n          \033[93m`---'\033[0m     |____/ \__,_|\___|_|\_\\\\__, |_|   \___/|_| \_\|_| |_| |_|\r\n                                           |___/                             \r\n\n\n"


//
// Variables
//
DEFVAR("EVT", 3, 0x00, EVT, 0x00000000)
DEFVAR("TEST-MODE", 9, 0x00, TEST_MODE, CONFIG_TEST_MODE)
DEFVAR("ECHO", 4, 0x00, ECHO, CONFIG_ECHO)
DEFVAR("UP", 2, 0x00, UP, USERSPACE_BASE)
DEFVAR("STATE", 5, 0x00, STATE, 0x00)
DEFVAR("DP", 2, 0x00, DP, USERSPACE_BASE)
DEFVAR("LATEST", 6, 0x00, LATEST, name_BYE)
DEFVAR("S0", 2, 0x00, SZ, 0xFFFFFF00)
DEFVAR("BASE", 4, 0x00, BASE, 10)
DEFVAR("SHOW-PROMPT", 11, 0x00, SHOW_PROMPT, 0x00)


DEFCODE("DUCKY", 5, F_HIDDEN, DUCKY)
  la r0, __ducky_welcome
  call putcs
  NEXT



DEFWORD("WELCOME", 7, 0x00, WELCOME)
  .word TEST_MODE
  .word FETCH
  .word NOT
  .word ZBRANCH
  .word 0x000000A8
  .word DUCKY
  .word SQUOTE_LITSTRING
  .word 0x63754413
  .word 0x4F46796B
  .word 0x20485452
  .word 0x53524556
  .word 0x204E4F49
  .word TELL
  .word VERSION
  .word DOT
  .word CR
  .word SQUOTE_LITSTRING
  .word 0x69754206
  .word 0x0020646C
  .word TELL
  .word BUILD_STAMP
  .word TYPE
  .word CR
  .word UNUSED
  .word DOT
  .word SQUOTE_LITSTRING
  .word 0x4C45430F
  .word 0x5220534C
  .word 0x49414D45
  .word 0x474E494E
  .word TELL
  .word CR
  .word SQUOTE_LITSTRING
  .word 0x70795413
  .word 0x42222065
  .word 0x20224559
  .word 0x65206F74
  .word 0x20746978
  .word TELL
  .word CR
  .word TRUE
  .word SHOW_PROMPT
  .word STORE
  .word TRUE
  .word ECHO
  .word STORE
  .word EXIT


DEFCODE("BUILD-STAMP", 11, 0x00, BUILD_STAMP)
  // ( -- addr u )
  push TOS
  la X, __build_stamp_length
  lb TOS, X
  inc X
  push X
  NEXT


DEFCODE("VMDEBUGON", 9, F_IMMED, VMDEBUGON)
  // ( -- )
  call __vmdebug_on
  NEXT


DEFCODE("VMDEBUGOFF", 10, F_IMMED, VMDEBUGOFF)
  // ( -- )
  call __vmdebug_off
  NEXT


DEFCODE("PROMPT", 6, 0x00, PROMPT)
  // ( flag -- )
  mov r0, TOS
  pop TOS
  call print_prompt
  NEXT


//****************************
//
// Terminal IO routines and words
//
//****************************

  /* Word buffer lies right next to its length, pretending it's a standard
   * counted string <length><chars...>. It starts at aligned address, to allow
   * seamless coopoeration with C code.
   */
  .section .bss
  .align CELL

  BYTE(word_buffer_length, 0x00)
  SPACE(word_buffer, WORD_BUFFER_SIZE)


DEFCODE("WORD", 4, 0x00, WORD)
  // ( char "<chars>ccc<char>" -- c-addr )
  mov r0, TOS
  call __read_word
  mov TOS, r0
  NEXT


DEFCODE("DWORD", 5, 0x00, DWORD)
  // ( "<chars>ccc<char>" -- c-addr )
  // like WORD but with space as a delimiter ("default WORD")
  call __read_dword
  push TOS
  mov TOS, r0
  NEXT


// fw_parse_result_t instance
  .section .bss
  .align CELL
__PARSE_result:
  .word 0x00000000  // pr_word = NULL
  .word 0x00000000  // pr_length = NULL

DEFCODE("PARSE", 5, 0x00, PARSE)
  // ( char "ccc<char>" -- c-addr u )
  //
  // Parse ccc delimited by the delimiter char.
  // c-addr is the address (within the input buffer) and u is the length
  // of the parsed string. If the parse area was empty, the resulting string
  // has a zero length.

  la W, __PARSE_result

  mov r0, TOS
  mov r1, W
  call do_PARSE

  // push pr_word
  lw X, W
  push X
  // push pr_length
  lw TOS, W[WORD_SIZE]
  NEXT


DEFCODE("ACCEPT", 6, 0x00, ACCEPT)
  // ( c-addr +n1 -- +n2 )
  mov r1, TOS
  pop r0
  call __read_line_from_kbd
  mov TOS, r0
  NEXT


DEFCODE("REFILL", 6, 0x00, REFILL)
  // ( -- flag )
  call do_REFILL
  push TOS
  mov TOS, r0
  NEXT


DEFCODE("KEY", 3, 0x00, KEY)
  // ( -- n )
  call __read_char
  push TOS
  mov TOS, r0
  NEXT


DEFCODE("EMIT", 4, 0x00, EMIT)
  // ( n -- )
  mov r0, TOS
  pop TOS
  call putc
  NEXT


DEFCODE("EVALUATE", 8, 0x00, EVALUATE)
  // ( i*x c-addr u -- j*x )
  //
  // Save the current input source specification. Store minus-one (-1)
  // in SOURCE-ID if it is present. Make the string described by c-addr
  // and u both the input source and input buffer, set >IN to zero, and
  // interpret. When the parse area is empty, restore the prior input
  // source specification. Other stack effects are due to the words EVALUATEd.
  mov r1, TOS
  pop r0
  pop TOS
  call do_EVALUATE
  NEXT


DEFCODE(">IN", 3, 0x00, TOIN)
  // ( -- a-addr )
  call do_TOIN
  push TOS
  mov TOS, r0
  NEXT


DEFCODE("TYPE", 4, 0x00, TYPE)
  // ( address length -- )
  mov r1, TOS
  pop r0
  pop TOS
  call puts
  NEXT


DEFCODE("SOURCE-ID", 9, 0x00, SOURCE_ID)
  push TOS
  la TOS, current_input  // TOS = &current_input
  lw TOS, TOS            // TOS = current_input, aka address of the current input desc
  lw TOS, TOS            // TOS = current_input->id_source_id
  NEXT


DEFCODE("SOURCE", 6, 0x00, SOURCE)
  // ( -- address length )
  //
  // c-addr is the address of, and u is the number of characters in,
  // the input buffer.
  la W, current_input
  lw W, W
  lw X, W[8]
  lw Y, W[12]

  push TOS
  lw TOS, W[8]
  push TOS
  lw TOS, W[12]
  NEXT


DEFCODE("RESTORE-INPUT", 13, 0x00, RESTORE_INPUT)
  // ( xn ... x1 n -- flag )
  mov r0, TOS
  mov r1, sp
  call do_RESTORE_INPUT
  add sp, 8
  li TOS, FORTH_FALSE
  NEXT


DEFCODE("SAVE-INPUT", 10, 0x00, SAVE_INPUT)
  // ( -- xn ... x1 n )
  push TOS
  sub sp, 8                            // make space for 2 items on stack
  mov r0, sp
  call do_SAVE_INPUT
  mov TOS, r0
  NEXT


  .data

  .type __found_word, word, 0x00000000

DEFCODE("FIND", 4, 0x00, FIND)
  // ( c-addr -- c-addr 0 | xt 1 | xt -1 )
  mov X, TOS                         // save c-addr for later
  mov r0, TOS
  la r1, __found_word
  call fw_search
  cmp r0, 0x00
  bz __FIND_notfound
  push r0 // save find's result for later
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  pop r1
  push r0
  mov TOS, r1
  j __FIND_next
__FIND_notfound:
  push X                              // saved c-addr
  li TOS, 0x00
__FIND_next:
  NEXT


DEFCODE("'", 1, F_IMMED, TICK)
  // ( "<spaces>name" -- xt )
  call __read_dword
  la r1, __found_word
  call fw_search
  cmp r0, 0x00
  bz __ERR_undefined_word
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  push TOS
  mov TOS, r0
  NEXT


DEFCODE("[']", 3, 0x00, BRACKET_TICK)
  push TOS
  lw TOS, FIP
  add FIP, CELL
  NEXT


DEFCODE(">CFA", 4, 0x00, TCFA)
  // ( address -- address )
  mov r0, TOS
  call do_TCFA
  mov TOS, r0
  NEXT


DEFWORD(">DFA", 4, 0x00, TDFA)
  .word TCFA
  .word LIT
  .word CELL
  .word ADD
  .word EXIT


DEFCODE("EXECUTE", 7, 0x00, EXECUTE)
  mov W, TOS
  pop TOS
  lw X, W
  j X


DEFCODE("LIT", 3, 0x00, LIT)
  push TOS
  lw TOS, FIP
  add FIP, CELL
  NEXT


DEFCODE(",", 1, 0x00, COMMA)
  // ( x -- )
  mov r0, TOS
  pop TOS
  call do_COMMA
  NEXT


DEFCODE("COMPILE,", 8, 0x00, COMPILE_COMMA)
  // ( xt -- )
  mov r0, TOS
  pop TOS
  call do_COMMA
  NEXT


DEFCODE("[", 1, F_IMMED, LBRAC)
  li W, 0x00
  la X, var_STATE
  stw X, W
  NEXT


DEFCODE("]", 1, 0x00, RBRAC)
  li W, 1
  la X, var_STATE
  stw X, W
  NEXT


DEFWORD(":", 1, 0x00, COLON)
  .word DWORD
  .word HEADER_COMMA
  .word LIT
  .word DOCOL
  .word COMMA
  .word LATEST
  .word FETCH
  .word HIDDEN
  .word RBRAC
  .word EXIT


DEFWORD(";", 1, F_IMMED, SEMICOLON)
  .word LIT
  .word EXIT
  .word COMMA
  .word LATEST
  .word FETCH
  .word HIDDEN
  .word LBRAC
  .word EXIT


DEFCODE("IMMEDIATE", 9, F_IMMED, IMMEDIATE)
  la W, var_LATEST
  lw X, W
  add X, WR_FLAGS
  lb Y, X
  or Y, F_IMMED
  stb X, Y
  NEXT


DEFCODE("HIDDEN", 6, 0x00, HIDDEN)
  // ( word_address -- )
  add TOS, WR_FLAGS
  lb X, TOS
  xor X, F_HIDDEN
  stb TOS, X
  pop TOS
  NEXT


DEFCODE("BRANCH", 6, 0x00, BRANCH)
  // ( -- )
  lw W, FIP
  add FIP, W
  NEXT


DEFCODE("0BRANCH", 7, 0x00, ZBRANCH)
  // ( n -- )
  mov W, TOS
  pop TOS
  cmp W, W
  bz code_BRANCH
  add FIP, CELL
  NEXT


  .section .bss
  .align CELL
__isnumber_result:
  .word 0x00000000
  .word 0x00000000

DEFCODE("?NUMBER", 7, 0x00, ISNUMBER)
  // ( c-addr -- n true | c-addr false )
  mov r0, TOS
  la r1, __isnumber_result
  call do_ISNUMBER
  cmp r0, 0x00
  bz __ISNUMBER_fail
  la W, __isnumber_result
  lw W, W
  push W
  j __ISNUMBER_next
__ISNUMBER_fail:
  push TOS
__ISNUMBER_next:
  mov TOS, r0
  j code_DOTS
  NEXT


  .section .bss
  .align CELL
__interpret_decision:
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000

  .text

__INTERPRET:
  push r0                              // save handler of EMPTY result

  la r0, __interpret_decision
  call do_INTERPRET

  pop r0

  la r1, __interpret_decision
  lw r2, r1
  bz __INTERPRET_next

  cmp r2, 0x01
  be r0

  cmp r2, 0x02
  be __INTERPRET_execute_word

  cmp r2, 0x03
  be __INTERPRET_execute_lit

  cmp r2, 0x04
  be __INTERPRET_execute_2lit

  j __ERR_interpret_fail

__INTERPRET_exit:
  POPRSP(FIP)
  NEXT

__INTERPRET_execute_word:
  lw W, r1[WORD_SIZE]
  lw X, W
  j X

__INTERPRET_execute_lit:
  push TOS
  lw TOS, r1[WORD_SIZE]
__INTERPRET_next:
  NEXT

__INTERPRET_execute_2lit:
  push TOS
  lw TOS, r1[CELL]
  push TOS
  lw TOS, r1[DOUBLECELL]
  NEXT


DEFCODE("INTERPRET", 9, 0x00, INTERPRET)
  la r0, __INTERPRET_next
  j __INTERPRET


DEFCODE("EMBED_INTERPRET", 10, 0x00, INTERPRET3)
  la r0, __INTERPRET_exit
  j __INTERPRET


DEFWORD("QUIT", 4, 0x00, QUIT)
  .word RZ                             // reset return stack
  .word RSPSTORE
  .word SOURCE_ID
  .word LIT
  .word 0x00
  .word STORE
  .word LBRAC
  .word REFILL                         // do the initial refill
  .word DROP                           // drop REFILL's return value
  .word INTERPRET                      // refill buffer, read word, execute them
  .word BRANCH                         // back to interpret
  .word -8


DEFCODE("ABORT", 5, 0x00, ABORT)
  la W, var_SZ
  lw sp, W

  // now this is tricky... jumping to QUIT
  la W, QUIT
  lw X, W
  j X


DEFWORD("HIDE", 4, 0x00, HIDE)
  .word DWORD
  .word FIND
  .word DROP
  .word HIDDEN
  .word EXIT


DEFCODE("EXIT", 4, 0x00, EXIT)
  POPRSP(FIP)
  NEXT


//
// Comparison ops
//

__CMP_true:
  LOAD_TRUE(TOS)
  NEXT

__CMP_false:
  LOAD_FALSE(TOS)
  NEXT


DEFCODE("=", 1, 0x00, EQU)
  // ( a b -- n )
  pop W
  cmp W, TOS
  TF_FINISH(EQU, be)


DEFCODE("<>", 2, 0x00, NEQU)
  // ( a b -- n )
  pop W
  cmp W, TOS
  TF_FINISH(NEQU, bne)


DEFCODE("0=", 2, 0x00, ZEQU)
  // ( n -- n )
  cmp TOS, 0x00
  TF_FINISH(ZEQU, bz)


DEFCODE("0<>", 3, 0x00, ZNEQU)
  // ( n -- n )
  cmp TOS, 0x00
  TF_FINISH(ZNEQU, bnz)


DEFCODE("<", 1, 0x00, LT)
  // ( a b -- n )
  pop W
  cmp W, TOS
  TF_FINISH(LT, bl)


DEFCODE(">", 1, 0x00, GT)
  pop W
  cmp W, TOS
  TF_FINISH(GT, bg)


DEFCODE("<=", 2, 0x00, LE)
  pop W
  cmp W, TOS
  TF_FINISH(LE, ble)


DEFCODE(">=", 2, 0x00, GE)
  pop W
  cmp W, TOS
  TF_FINISH(GE, bge)


DEFCODE("0<", 2, 0x00, ZLT)
  // ( n -- flag )
  // flag is true if and only if n is less than zero
  cmp TOS, 0x00
  TF_FINISH(ZLT, bl)


DEFCODE("0>", 2, 0x00, ZGT)
  // ( n -- flag )
  // flag is true if and only if n is greater than zero
  cmp TOS, 0x00
  TF_FINISH(ZGT, bg)


DEFCODE("0<=", 3, 0x00, ZLE)
  cmp TOS, 0x00
  TF_FINISH(ZLE, ble)


DEFCODE("0>=", 3, 0x00, ZGE)
  cmp TOS, 0x00
  TF_FINISH(ZGE, bge)


DEFCODE("?DUP", 4, 0x00, QDUP)
  cmp TOS, 0x00
  bnz __QDUP_nonzero
  li TOS, 0x00
  NEXT
__QDUP_nonzero:
  push TOS
  NEXT


//
// Arthmetic operations
//
DEFCODE("+", 1, 0x00, ADD)
  // ( a b -- a+b )
  pop W
  add TOS, W
  NEXT


DEFCODE("-", 1, 0x00, SUB)
  // ( a b -- a-b )
  pop W
  sub W, TOS
  mov TOS, W
  NEXT


DEFCODE("1+", 2, 0x00, INCR)
  // ( a -- a+1 )
  inc TOS
  NEXT


DEFCODE("1-", 2, 0x00, DECR)
  // ( a -- a-1 )
  dec TOS
  NEXT


DEFCODE("2+", 2, 0x00, INCR2)
  // ( a -- a+2 )
  add TOS, 2
  NEXT


DEFCODE("2-", 2, 0x00, DECR2)
  // ( a -- a-2 )
  sub TOS, 2
  NEXT


DEFCODE("4+", 2, 0x00, INCR4)
  // ( a -- a+4 )
  add TOS, 4
  NEXT


DEFCODE("4-", 2, 0x00, DECR4)
  // ( a -- a-4 )
  sub TOS, 4
  NEXT


DEFCODE("*", 1, 0x00, MUL)
  // ( a b -- a*b )
  pop W
  mul TOS, W
  NEXT


DEFCODE("/", 1, 0x00, DIV)
  // ( a b -- <a / b> )
  pop W
  div W, TOS
  mov TOS, W
  NEXT


DEFCODE("MOD", 3, 0x00, MOD)
  // ( a b -- <a % b> )
  pop W
  mod W, TOS
  mov TOS, W
  NEXT


DEFCODE("/MOD", 4, 0x00, DIVMOD)
  // ( a b -- <a % b> <a / b> )
  pop W
  mov X, W
  div W, TOS
  mod X, TOS
  push X
  mov TOS, W
  NEXT


DEFCODE("AND", 3, 0x00, AND)
  // ( x1 x2 -- <x1  x2> )
  pop W
  and TOS, W
  NEXT


DEFCODE("OR", 2, 0x00, OR)
  pop W
  or TOS, W
  NEXT


DEFCODE("XOR", 3, 0x00, XOR)
  pop W
  xor TOS, W
  NEXT


DEFCODE("INVERT", 6, 0x00, INVERT)
  not TOS
  NEXT


//
// Parameter stack operations
//

DEFCODE("DROP", 4, 0x00, DROP)
  // ( n -- )
  pop TOS
  NEXT


DEFCODE("SWAP", 4, 0x00, SWAP)
  // ( a b -- b a )
  pop W
  push TOS
  mov TOS, W
  NEXT


DEFCODE("DUP", 3, 0x00, DUP)
  // ( a -- a a )
  push TOS
  NEXT


DEFCODE("OVER", 4, 0x00, OVER)
  // ( a b -- a b a )
  push TOS
  lw TOS, sp[CELL]
  NEXT


DEFCODE("ROT", 3, 0x00, ROT)
  // ( a b c -- b c a )
  lw W, sp[4]                         // a
  lw X, sp                            // b
  stw sp[4], X
  stw sp, TOS
  mov TOS, W
  NEXT


DEFCODE("-ROT", 4, 0x00, NROT)
  // ( a b c -- c a b )
  lw W, sp[4]                         // a
  lw X, sp                            // b
  stw sp[4], TOS
  stw sp, W
  mov TOS, X
  NEXT


DEFCODE("2DROP", 5, 0x00, TWODROP)
  // ( n n -- )
  pop TOS
  pop TOS
  NEXT


DEFCODE("2DUP", 4, 0x00, TWODUP)
  // ( a b -- a b a b )
  lw W, sp
  push TOS
  push W
  NEXT


DEFCODE("2SWAP", 5, 0x00, TWOSWAP)
  // ( a b c d -- c d a b )
  lw W, sp[8] // a
  lw X, sp[4] // b
  lw Y, sp    // c
  stw sp[8], Y
  stw sp[4], TOS
  stw sp,    W
  mov TOS, X
  NEXT


//
// Input and output
//

DEFCODE("CHAR", 4, 0x00, CHAR)
  // ( -- n )
  call __read_dword
  inc r0
  push TOS
  lb TOS, r0
  NEXT


DEFCODE("[CHAR]", 6, F_IMMED, BRACKETCHAR)
  call __read_dword
  inc r0
  lb W, r0
  la r0, LIT
  call do_COMMA
  mov r0, W
  call do_COMMA
  NEXT


//
// Return stack
//

DEFCODE(">R", 2, 0x00, TOR)
  PUSHRSP(TOS)
  pop TOS
  NEXT


DEFCODE("R>", 2, 0x00, FROMR)
  push TOS
  POPRSP(TOS)
  NEXT


DEFCODE("RSP@", 4, 0x00, RSPFETCH)
  push TOS
  mov TOS, RSP
  NEXT


DEFCODE("RSP!", 4, 0x00, RSPSTORE)
  mov RSP, TOS
  pop TOS
  NEXT


DEFCODE("RDROP", 5, 0x00, RDOP)
  POPRSP(W)
  NEXT


DEFCODE("R@", 2, 0x00, RFETCH)
  // ( -- x ) ( R:  x -- x )
  push TOS
  lw TOS, RSP
  NEXT


//
// Parameter stack
//

DEFCODE("DSP@", 4, 0x00, DSPFETCH)
  push TOS
  mov TOS, sp
  NEXT


DEFCODE("DSP!", 4, 0x00, DSPSTORE)
  mov sp, TOS
  pop TOS
  NEXT


//
// Memory operations
//
DEFCODE("!", 1, 0x00, STORE)
  // ( data address -- )
  pop W
  stw TOS, W
  pop TOS
  NEXT


DEFCODE("@", 1, 0x00, FETCH)
  // ( address -- n )
  lw TOS, TOS
  NEXT


DEFCODE("+!", 2, 0x00, ADDSTORE)
  // ( amount address -- )
  pop W
  lw Y, TOS
  add Y, W
  stw TOS, Y
  pop TOS
  NEXT


DEFCODE("-!", 2, 0x00, SUBSTORE)
  // ( amount address -- )
  pop W
  lw Y, TOS
  sub Y, W
  stw TOS, Y
  pop TOS
  NEXT


DEFCODE("C!", 2, 0x00, STOREBYTE)
  // ( data address -- )
  pop W
  stb TOS, W
  pop TOS
  NEXT


DEFCODE("C@", 2, 0x00, FETCHBYTE)
  // ( address -- n )
  lb TOS, TOS
  NEXT


//
// Strings
//

DEFCODE("SQUOTE_LITSTRING", 9, 0x00, SQUOTE_LITSTRING)
  // ( -- c-addr u )
  lb W, FIP     // load length
  inc FIP        // FIP points to string
  push TOS
  push FIP
  mov TOS, W
  add FIP, W    // skip string
  ALIGN_CELL(FIP)    // align FIP
  NEXT


DEFCODE("CQUOTE_LITSTRING", 9, 0x00, CQUOTE_LITSTRING)
  // ( -- c-addr )
  push TOS
  mov TOS, FIP
  lb W, FIP     // load string length
  inc FIP        // skip length
  add FIP, W    // skip string
  ALIGN_CELL(FIP)    // align FIP
  NEXT


DEFCODE("TELL", 4, 0x00, TELL)
  // ( c-addr u -- )
  pop r0
  mov r1, TOS
  pop TOS
  call puts
  NEXT


//
// Loop helpers
//

DEFCODE("(DO)", 4, 0x00, PAREN_DO)
  // ( control index -- )
  pop X
  PUSHRSP(X)
  PUSHRSP(TOS)
  pop TOS
  NEXT


DEFCODE("(LOOP)", 6, 0x00, PAREN_LOOP)
  POPRSP(W) // index
  POPRSP(X) // control
  inc W
  cmp W, X
  be __PAREN_LOOP_next
  PUSHRSP(X)
  PUSHRSP(W)
  lw W, FIP
  add FIP, W
  NEXT
__PAREN_LOOP_next:
  add FIP, CELL
  NEXT


DEFCODE("(+LOOP)", 7, 0x00, PAREN_PLUS)
  POPRSP(W) // index
  POPRSP(X) // control
  mov Z, W  // save old index for later
  add W, TOS
  pop TOS
  sub Z, X  // (index - limit)
  mov Y, W  // (index + n)
  sub Y, X  // (index - limit + n)
  xor Z, Y
  bs __PARENPLUS_next
  PUSHRSP(X)
  PUSHRSP(W)
  lw W, FIP
  add FIP, W
  NEXT
__PARENPLUS_next:
  add FIP, CELL
  NEXT


DEFCODE("UNLOOP", 6, 0x00, UNLOOP)
  add RSP, 8 // CELL * 2
  NEXT


DEFCODE("I", 1, 0x00, I)
  push TOS
  lw TOS, RSP
  NEXT


DEFCODE("J", 1, 0x00, J)
  push TOS
  lw TOS, RSP[8]
  NEXT


DEFDOESWORD("LEAVE-SP", 8, 0x00, LEAVE_SP)
  .word 0x00000000
__LEAVE_SP_payload:
  .word __LEAVE_SP_payload
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000
  .word 0x00000000


DEFWORD("LEAVE", 5, F_IMMED, LEAVE)
  .word BRACKET_TICK
  .word UNLOOP
  .word COMMA
  .word BRACKET_TICK
  .word BRANCH
  .word COMMA
  .word LEAVE_SP
  .word FETCH
  .word LEAVE_SP
  .word SUB
  .word LIT
  .word 0x0000001F
  .word CELLS
  .word GT
  .word ZBRANCH
  .word 0x00000008
  .word ABORT
  .word LIT
  .word 0x00000001
  .word CELLS
  .word LEAVE_SP
  .word ADDSTORE
  .word HERE
  .word LEAVE_SP
  .word FETCH
  .word STORE
  .word LIT
  .word 0x00000000
  .word COMMA
  .word EXIT


DEFWORD("RESOLVE-DO", 10, 0x00, RESOLVE_DO)
  .word ZBRANCH
  .word 0x00000044
  .word DUP
  .word HERE
  .word SUB
  .word COMMA
  .word DUP
  .word LIT
  .word 0x00000002
  .word CELLS
  .word SUB
  .word HERE
  .word OVER
  .word SUB
  .word SWAP
  .word STORE
  .word BRANCH
  .word 0x00000014
  .word DUP
  .word HERE
  .word SUB
  .word COMMA
  .word EXIT


DEFWORD("RESOLVE-LEAVES", 14, 0x00, RESOLVE_LEAVES)
  .word LEAVE_SP
  .word FETCH
  .word FETCH
  .word OVER
  .word GT
  .word LEAVE_SP
  .word FETCH
  .word LEAVE_SP
  .word GT
  .word AND
  .word ZBRANCH
  .word 0x00000048
  .word HERE
  .word LEAVE_SP
  .word FETCH
  .word FETCH
  .word SUB
  .word LEAVE_SP
  .word FETCH
  .word FETCH
  .word STORE
  .word LIT
  .word 0x00000001
  .word CELLS
  .word NEGATE
  .word LEAVE_SP
  .word ADDSTORE
  .word BRANCH
  .word 0xFFFFFF90
  .word DROP
  .word EXIT


DEFWORD("DO", 2, F_IMMED, DO)
  .word BRACKET_TICK
  .word PAREN_DO
  .word COMMA
  .word HERE
  .word LIT
  .word 0x00000000
  .word EXIT


DEFWORD("?DO", 3, F_IMMED, QUESTIONDO)
  .word BRACKET_TICK
  .word TWODUP
  .word COMMA
  .word BRACKET_TICK
  .word NEQU
  .word COMMA
  .word BRACKET_TICK
  .word ZBRANCH
  .word COMMA
  .word LIT
  .word 0x00000000
  .word COMMA
  .word BRACKET_TICK
  .word PAREN_DO
  .word COMMA
  .word HERE
  .word LIT
  .word 0x00000001
  .word EXIT


DEFWORD("LOOP", 4, F_IMMED, LOOP)
  .word BRACKET_TICK
  .word PAREN_LOOP
  .word COMMA
  .word RESOLVE_DO
  .word RESOLVE_LEAVES
  .word EXIT


DEFWORD("+LOOP", 5, F_IMMED, PLUSLOOP)
  .word BRACKET_TICK
  .word PAREN_PLUS
  .word COMMA
  .word RESOLVE_DO
  .word RESOLVE_LEAVES
  .word EXIT


//
// Constants
//
DEFCODE("VERSION", 7, 0x00, VERSION)
  push TOS
  li TOS, FORTH_VERSION
  NEXT


DEFCODE("R0", 2, 0x00, RZ)
  push TOS
  la TOS, rstack_top
  lw TOS, TOS
  NEXT


DEFCODE("DOCOL", 5, 0x00, __DOCOL)
  push TOS
  la TOS, DOCOL
  NEXT


DEFCODE("F_IMMED", 7, 0x00, __F_IMMED)
  push TOS
  li TOS, F_IMMED
  NEXT


DEFCODE("F_HIDDEN", 8, 0x00, __F_HIDDEN)
  push TOS
  li TOS, F_HIDDEN
  NEXT


DEFCODE("TRUE", 4, 0x00, TRUE)
  push TOS
  LOAD_TRUE(TOS)
  NEXT


DEFCODE("FALSE", 5, 0x00, FALSE)
  push TOS
  LOAD_FALSE(TOS)
  NEXT


DEFCODE("DODOES", 6, 0x00, __DODOES)
  push TOS
  la TOS, DODOES
  NEXT


DEFWORD("CONSTANT", 8, 0x00, CONSTANT)
  .word DWORD
  .word HEADER_COMMA
  .word __DOCOL
  .word COMMA
  .word BRACKET_TICK
  .word LIT
  .word COMMA
  .word COMMA
  .word BRACKET_TICK
  .word EXIT
  .word COMMA
  .word EXIT


DEFWORD("VARIABLE", 8, 0x00, VARIABLE)
  .word DWORD
  .word HEADER_COMMA
  .word __DODOES
  .word COMMA
  .word LIT
  .word 0x00
  .word COMMA
  .word LIT
  .word 1
  .word CELLS
  .word ALLOT
  .word EXIT


DEFWORD("CREATE", 6, 0x00, CREATE)
  .word DWORD
  .word HEADER_COMMA
  .word __DODOES
  .word COMMA
  .word LIT
  .word 0x00
  .word COMMA
  .word EXIT


DEFWORD("DOES>", 5, 0x00, DOESTO)
  .word FROMR
  .word LATEST
  .word FETCH
  .word TDFA
  .word STORE
  .word EXIT


DEFWORD("VALUE", 5, 0x00, VALUE)
  .word DWORD
  .word HEADER_COMMA
  .word __DOCOL
  .word COMMA
  .word BRACKET_TICK
  .word LIT
  .word COMMA
  .word COMMA
  .word BRACKET_TICK
  .word EXIT
  .word COMMA
  .word EXIT


DEFCODE("TO", 2, F_IMMED, TO)
  call __read_dword
  la r1, __found_word
  call fw_search
  cmp r0, 0x00
  bz __ERR_undefined_word
  la r0, __found_word
  lw r0, r0
  call do_TCFA
  add r0, CELL                        // point to Data Field
  add r0, CELL                        // point to value field

  la W, var_STATE
  lw W, W
  bz __TO_store

  la W, var_DP
  lw X, W

  la Z, LIT
  stw X, Z
  add X, CELL

  stw X, r0
  add X, CELL

  la Z, STORE
  stw X, Z
  add X, CELL

  stw W, X
  j __TO_quit

__TO_store:
  stw r0, TOS
  pop TOS
__TO_quit:
  NEXT


// Include non-kernel words
#include "ducky-forth-words.s"
#include "words/double-cell-ints.s"
#include "words/compile.s"
#include "words/core-ext.s"
#include "words/block.s"
#include "words/double.s"
#include "words/number.s"


DEFCSTUB("\\\\", 1, F_IMMED, BACKSLASH)


DEFCODE("HERE", 4, 0x00, HERE)
  push TOS
  la TOS, var_DP
  lw TOS, TOS
  NEXT


DEFCODE("CRASH", 5, 0x00, CRASH)
  hlt 0x4FFF

DEFCODE("CRASH-NOW", 9, F_IMMED, CRASH_NOW)
  hlt 0x4FFF


/*
 * The last command - if it's not the last one, modify initial value of LATEST
 */
DEFCSTUB("BYE", 3, 0x00, BYE)
