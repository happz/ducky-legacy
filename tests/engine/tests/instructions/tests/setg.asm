  .include "defs.asm"
main:
  li r0, 0xEE
  li r1, 0xFF
  li r2, 0xFF
  li r2, 0xFF

  cmp r0, 0xDD
  setg r1 ; 1

  cmp r0, 0xEE
  setg r2 ; 0

  cmp r0, 0xFF
  setg r3 ; 0

  int $INT_HALT
