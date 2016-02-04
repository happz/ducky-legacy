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
  popw ; n
  push ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "M*", 2, 0, MSTAR
  ; ( n1 n2 -- d )
  sis $MATH_INST_SET
  popw ; n2
  popw ; n1
  mull ; d
  push ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "UM*", 3, 0, UMSTAR
  ; ( u1 u2 -- ud )
  sis $MATH_INST_SET
  popuw ; u2
  popuw ; u1
  mull  ; d
  push  ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "SM/REM", 6, 0, SMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
  popw    ; n1
  pop     ; n1 d1
  swap    ; d1 n1
  dup2    ; d1 n1 d1 n1
  symmodl ; d1 n1 n2
  pushw   ; d1 n1
  symdivl ; n3
  pushw   ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "FM/MOD", 6, 0, FMMOD
  ; ( d1 n1 -- n2 n3 )
  sis $MATH_INST_SET
  popw  ; n1
  pop   ; n1 d1
  swap  ; d1 n1
  dup2  ; d1 n1 d1 n1
  modl  ; d1 n1 n2
  pushw ; d1 n1
  divl  ; n2
  pushw ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "UM/MOD", 6, 0, UMMOD
  ; ( ud u1 -- u2 u3 )
  sis $MATH_INST_SET
  popuw ; u1
  pop   ; u1 ud
  swap  ; ud u1
  dup2  ; ud u1 ud u1
  modl  ; ud u1 u2
  pushw ; ud u1
  divl  ; u3
  pushw ;
  sis $DUCKY_INST_SET
  $NEXT


$DEFCODE "*/", 2, 0, STARSLASH
  ; ( n1 n2 n3 -- n4 )
  pop $W ; n3
  pop $X ; n2
  pop $Y ; n1
  mul $X, $Y
  div $X, $W
  push $X
  $NEXT

$DEFCODE "*/MOD", 5, 0, STARMOD
  ; ( n1 n2 n3 -- n4 n5 )
  pop $W ; n3
  pop $X ; n2
  pop $Y ; n1
  mul $Y, $X
  mov $X, $Y
  div $X, $W
  mod $Y, $W
  push $Y
  push $X
  $NEXT
