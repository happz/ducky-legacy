; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "defs.asm"

.def DUCKY_VERSION: 0x0001

.def TEXT_OFFSET:    0x0000
.def USERSPACE_BASE: 0x5000

; RTC frequency - 1 tick per second is good enough for us.
.def RTC_FREQ:        0x0001

; One cell is 16 bits, 2 bytes, this is 16-bit FORTH. I hope it's clear now :)
.def CELL:               2

; This is actually 8192 - first two bytes are used by HERE_INIT
; needed for HERE inicialization. HERE_INIT's space can be then
; reused as userspace
.def USERSPACE_SIZE:   8192

; 32 cells
.def RSTACK_SIZE:        64

; Allow for 8 nested EVALUATE calls
.def INPUT_STACK_SIZE:   64

; Let's say the longest line can be 512 chars...
.def INPUT_BUFFER_SIZE: 512

; 32 chars should be enough for any word
.def WORD_SIZE:          32

; 32 cells, should be enough
.def RSTACK_SIZE: 64

; 255 chars should be enough for a string length (and it fits into 1 byte)
.def STRING_SIZE:       255

; Some commonly used registers
.def FIP: r12
.def PSP: sp
.def RSP: r11
.def W:   r10
.def X:   r9
.def Y:   r8
.def Z:   r7

; Offsets of word header fields
;
; +-------------+ <- 0; label "name_$WORD"
; | link        |
; |             |
; +-------------+ <- 2
; | name CRC    |
; |             |
; +-------------+ <- 4
; | flags       |
; +-------------+ <- 5
; | name length |
; +-------------+ <- 6
; | name        |
; .             .
; .             .
; .             .
; |             |
; +-------------+ <- 6 + name length + padding byte
; | codeword    |
; |             |
; +-------------+ <- 8 + name length + padding byte
;
.def wr_link:     0
.def wr_namecrc:  2
.def wr_flags:    4
.def wr_namelen:  5
.def wr_name:     6

; Word flags
.def F_IMMED:  0x0001
.def F_HIDDEN: 0x0002

; FORTH boolean "flags"
.def FORTH_TRUE:  0xFFFF
.def FORTH_FALSE: 0x0000

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
  .int 0x79
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
  .int 0x79
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

.macro align_page reg:
  add #reg, $PAGE_SIZE
  dec #reg
  and #reg, $PAGE_MASK
.end

.macro unpack_word_for_find:
  mov r1, r0    ; copy c-addr to r1
  inc r0        ; point r0 to string
  lb r1, r1     ; load string length
.end
