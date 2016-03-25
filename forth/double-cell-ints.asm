; A minimal FORTH kernel for Ducky virtual machine
;
; This was written as an example and for educating myself, no higher ambitions intended.
;
; Heavily based on absolutely amazing FORTH tutorial by
; Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
;
;
; This file contains implementation of FORTH words for arithmetics
; of double-cell integers.
;
; So far it is not complete yet - while it passes most of the tests
; from the ANS FORTH test suite, it fails on some of them, mainly in
; "gray" areas of dividing maximal values of data types. And, of course,
; it still depends on using a mathematical coprocessor. One day it might
; be nice to have native implementations of necessary "instructions",
; written in pure assembly.
;

.include "ducky-forth-defs.asm"
.include "math.asm"


$DEFCODE "S>D", 3, 0, STOD
  ; ( n -- d )
  sis $MATH_INST_SET
.ifdef FORTH_TIR
  loadw $TOS     ; n
  save $TOS, $W  ;
  sis $DUCKY_INST_SET
  push $W
.else
  popw ; n
  push ;
  sis $DUCKY_INST_SET
.endif
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
.ifdef FORTH_TIR
  sis $MATH_INST_SET
  loadw $TOS ; n2
  popw       ; n2 n1
  mull       ; d
  save $TOS, $W
  sis $DUCKY_INST_SET
  push $W
.else
  sis $MATH_INST_SET
  popw ; n2
  popw ; n1
  mull ; d
  push ;
  sis $DUCKY_INST_SET
.endif
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- ud )
.ifdef FORTH_TIR
  sis $MATH_INST_SET
  loaduw $TOS ; u2
  popuw       ; u2 u1
  mull        ; d
  save $TOS, $W
  sis $DUCKY_INST_SET
  push $W
.else
  sis $MATH_INST_SET
  popuw ; u2
  popuw ; u1
  mull  ; d
  push  ;
  sis $DUCKY_INST_SET
.endif
  $NEXT


$DEFCODE "SM/REM", 6, 0, SMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
.ifdef FORTH_TIR
  loadw $TOS ; n1          | d1
  pop        ; n1 d1       |
  swp        ; d1 n1       |
  dup2       ; d1 n1 d1 n1 |
  symmodl    ; d1 n1 n2    |
  pushw      ; d1 n1       | n2
  symdivl    ; n3          | n2
  savew $TOS ;             | n2 n3
.else
  popw    ; n1
  pop     ; n1 d1
  swp     ; d1 n1
  dup2    ; d1 n1 d1 n1
  symmodl ; d1 n1 n2
  pushw   ; d1 n1
  symdivl ; n3
  pushw   ;
.endif
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "FM/MOD", 6, 0, FMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
.ifdef FORTH_TIR
  loadw $TOS ; n1          | d1
  pop        ; n1 d1       |
  swp        ; d1 n1       |
  dup2       ; d1 n1 d1 n1 |
  modl       ; d1 n1 n2    |
  pushw      ; d1 n1       | n2
  divl       ; n3          | n2
  savew $TOS ;             | n2 n3
.else
  popw  ; n1
  pop   ; n1 d1
  swp   ; d1 n1
  dup2  ; d1 n1 d1 n1
  modl  ; d1 n1 n2
  pushw ; d1 n1
  divl  ; n2
  pushw ;
.endif
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "UM/MOD", 6, 0, UMMOD
  ; ( ud u1 -- u2 u3 )
  sis $MATH_INST_SET
.ifdef FORTH_TIR
  loaduw $TOS
  pop
  swp
  dup2
  modl
  pushw
  divl
  savew $TOS
.else
  popuw ; u1
  pop   ; u1 ud
  swp   ; ud u1
  dup2  ; ud u1 ud u1
  modl  ; ud u1 u2
  pushw ; ud u1
  divl  ; u3
  pushw ;
.endif
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "*/", 2, 0, STARSLASH
  ; ( n1 n2 n3 -- n4 )
.ifdef FORTH_TIR
  sis $MATH_INST_SET
  popw
  popw
  mull
  loadw $TOS
  divl
  savew $TOS
  sis $DUCKY_INST_SET
.else
  sis $MATH_INST_SET
  popw   ; n3
  popw   ; n2
  popw   ; n1
  mull
  swp
  divl
  pushw
  sis $DUCKY_INST_SET
.endif
  $NEXT

$DEFCODE "*/MOD", 5, 0, STARMOD
  ; ( n1 n2 n3 -- n4 n5 )
.ifdef FORTH_TIR
  sis $MATH_INST_SET
  popw
  popw
  mull
  dup
  loadw $TOS
  modl
  pushw
  loadw $TOS
  divl
  savew $TOS
  sis $DUCKY_INST_SET
.else
  sis $MATH_INST_SET
  popw   ; n3
  popw   ; n3 n2
  popw   ; n3 n2 n1
  mull   ; n3 (n2 * n1)
  swp    ; (n2 * n1) n3
  dup2   ; (n2 * n1) n3 (n2 * n1) n3
  modl
  pushw
  divl
  pushw
  sis $DUCKY_INST_SET
.endif
  $NEXT
