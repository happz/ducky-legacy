  .include "defs.asm"
main:
  li r0, 1
  li r1, 0
  cmp r0, r1
  int $INT_HALT