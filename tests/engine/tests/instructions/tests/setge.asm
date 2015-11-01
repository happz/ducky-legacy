  .include "defs.asm"
main:
  li r0, 0xEE
  li r1, 0xFF
  li r2, 0xFF
  li r2, 0xFF

  cmp r0, 0xDD
  setge r1 ; 1

  cmp r0, 0xEE
  setge r2 ; 1

  cmp r0, 0xFF
  setge r3 ; 0

  int $INT_HALT
