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

.include "ducky-forth-defs.s"
.include "arch/math.hs"


$DEFCODE "S>D", 3, 0, STOD
  ; ( n -- d )
  sis $MATH_INST_SET
  loadw $TOS     ; n
  save $TOS, $W  ;
  sis $DUCKY_INST_SET
  push $W
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
  sis $MATH_INST_SET
  loadw $TOS ; n2
  popw       ; n2 n1
  mull       ; d
  save $TOS, $W
  sis $DUCKY_INST_SET
  push $W
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- ud )
  sis $MATH_INST_SET
  loaduw $TOS ; u2
  popuw       ; u2 u1
  mull        ; d
  save $TOS, $W
  sis $DUCKY_INST_SET
  push $W
  $NEXT


$DEFCODE "SM/REM", 6, 0, SMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
  loadw $TOS ; n1          | d1
  pop        ; n1 d1       |
  swp        ; d1 n1       |
  dup2       ; d1 n1 d1 n1 |
  symmodl    ; d1 n1 n2    |
  pushw      ; d1 n1       | n2
  symdivl    ; n3          | n2
  savew $TOS ;             | n2 n3
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "FM/MOD", 6, 0, FMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
  loadw $TOS ; n1          | d1
  pop        ; n1 d1       |
  swp        ; d1 n1       |
  dup2       ; d1 n1 d1 n1 |
  modl       ; d1 n1 n2    |
  pushw      ; d1 n1       | n2
  divl       ; n3          | n2
  savew $TOS ;             | n2 n3
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "UM/MOD", 6, 0, UMMOD
  ; ( ud u1 -- u2 u3 )
  sis $MATH_INST_SET
  loaduw $TOS
  pop
  swp
  dup2
  umodl
  pushw
  udivl
  savew $TOS
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "*/", 2, 0, STARSLASH
  ; ( n1 n2 n3 -- n4 )
  sis $MATH_INST_SET
  popw
  popw
  mull
  loadw $TOS
  divl
  savew $TOS
  sis $DUCKY_INST_SET
  $NEXT

$DEFCODE "*/MOD", 5, 0, STARMOD
  ; ( n1 n2 n3 -- n4 n5 )
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
  $NEXT
