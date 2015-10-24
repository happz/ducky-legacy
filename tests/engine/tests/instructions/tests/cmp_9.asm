  .include "defs.asm"
main:
  li r0, 20
  li r1, 10
  cmp r0, r1
  int $INT_HALT
