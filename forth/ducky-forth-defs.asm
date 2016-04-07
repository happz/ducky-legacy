; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;

.include "ducky.asm"

.def DUCKY_VERSION: 0x0002

.def TEXT_BASE:      0x0000
.def USERSPACE_BASE: 0x5000

; RTC frequency - 1 tick per second is good enough for us.
.ifndef RTC_FREQ
.def RTC_FREQ:        0x0001
.endif

; One cell is 32 bits, 4 bytes, this is 32-bit FORTH. I hope it's clear now :)
.def CELL:               4
.def HALFCELL:           2

; This is actually 8192 - first four bytes are used by HERE_INIT
; needed for HERE inicialization. HERE_INIT's space can be then
; reused as userspace
.def USERSPACE_SIZE:   8192

; 64 cells
.def DSTACK_SIZE:        256

; 64 cells
.def RSTACK_SIZE:        256

; Allow for 8 nested EVALUATE calls
.def INPUT_STACK_SIZE:   128

; Let's say the longest line we can get from terminal is 512 characters
.def TERM_INPUT_BUFFER_SIZE: 512

; Let's say the longest line can be 512 chars...
.def INPUT_BUFFER_SIZE: 512

; 32 chars should be enough for any word
.def WORD_BUFFER_SIZE:   32

;
.def PNO_BUFFER_SIZE:   64

; 255 chars should be enough for a string length (and it fits into 1 byte)
.def STRING_SIZE:       255

; Some commonly used registers
.def FIP: r28
.def PSP: sp
.def RSP: r27
.def W:   r26
.def X:   r25
.def Y:   r24
.def Z:   r23
.ifdef FORTH_TIR
.def TOS: r22
.endif

.ifdef FORTH_DEBUG
.def LSP: r19
.endif


; Offsets of word header fields
;
; +-------------+ <- 0; label "name_$WORD"
; | link        |
; |             |
; +-------------+ <- 4
; | name CRC    |
; |             |
; +-------------+ <- 6
; | flags       |
; +-------------+ <- 7
; | name length |
; +-------------+ <- 8
; | name        |
; .             .
; .             .
; .             .
; |             |
; +-------------+ <- 8 + name length + padding bytes
; | codeword    |
; |             |
; +-------------+ <- 8 + name length + padding bytes + 4
;
.def wr_link:     0
.def wr_namecrc:  4
.def wr_flags:    6
.def wr_namelen:  7
.def wr_name:     8

; Word flags
.def F_IMMED:  0x0001
.def F_HIDDEN: 0x0002

; FORTH boolean "flags"
.def FORTH_TRUE:  0xFFFFFFFF
.def FORTH_FALSE: 0x00000000

.macro pushrsp reg:
  sub $RSP, $CELL
  stw $RSP, #reg
.end

.macro poprsp reg:
  lw #reg, $RSP
  add $RSP, $CELL
.end

.macro log_word reg:
.ifdef FORTH_DEBUG
  sub $LSP, $CELL
  stw $LSP, #reg
.endif
.end

.macro NEXT:
  ; FIP points to a cell with address of a Code Field,
  ; and Code Field contains address of routine

  lw $W, $FIP      ; W = address of a Code Field
  add $FIP, $CELL  ; move FIP to next cell in thread
  lw $X, $W        ; X = address of routine
  $log_word $W
  $log_word $X
  j $X
.end

.macro DEFWORD name, len, flags, label:
  .section .rodata
  .align 4

  .type name_#label, int
  .int link
  .set link, &name_#label

  .type __crc_#label, short
  .short 0x7979

  .type __flags_#label, byte
  .byte #flags

  .type __len_#label, byte
  .byte #len

  .type __name_#label, ascii
  .ascii #name

  .align 4
  .type #label, int
  .int &DOCOL
.end

.macro DEFCODE name, len, flags, label:
  .section .rodata
  .align 4

  .type name_#label, int
  .int link
  .set link, &name_#label

  .type __crc_#label, short
  .short 0x7979

  .type __flags_#label, byte
  .byte #flags

  .type __len_#label, byte
  .byte #len

  .type __name_#label, ascii
  .ascii #name

  .align 4
  .type #label, int
  .int &code_#label

  .text
code_#label:
.ifdef FORTH_TIR
  $log_word $TOS
  lw $W, sp
  $log_word $W
  $log_word sp
.else
  lw $W, sp
  $log_word $W
  lw $W, sp[4]
  $log_word $W
  $log_word sp
.endif
.end

.macro DEFVAR name, len, flags, label, initial:
  $DEFCODE #name, #len, #flags, #label
.ifdef FORTH_TIR
  push $TOS
  la $TOS, &var_#label
.else
  la $W, &var_#label
  push $W
.endif
  $NEXT

  .data
  .align 4
  .type var_#label, int
  .int #initial
.end

.macro load_minus_one reg:
  li #reg, 0xFFFF
  liu #reg, 0xFFFF
.end

.macro load_true reg:
  li #reg, 0xFFFF
  liu #reg, 0xFFFF
.end

.macro load_false reg:
  li #reg, 0x0000
  liu #reg, 0x0000
.end

.macro push_true reg:
  $load_true #reg
  push #reg
.end

.macro push_false:
  push 0x0000
.end

.macro align2 reg:
  inc #reg
  and #reg, 0x7FFE
.end

.macro align4 reg:
  add #reg, 3
  and #reg, 0x7FFC
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

.macro boot_progress:
  ; li r20, 0x2E
  ; outb $TTY_PORT_DATA, r20
.end

.def ERR_UNKNOWN:             -1
.def ERR_UNDEFINED_WORD:      -2
.def ERR_UNHANDLED_IRQ:       -3
.def ERR_NO_INTERPRET_SEMANTICS: -4
