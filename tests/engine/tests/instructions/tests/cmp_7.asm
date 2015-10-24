  .include "defs.asm"
main:
  li r0, 10
  li r1, 20
  cmp r0, r1
  int $INT_HALT
