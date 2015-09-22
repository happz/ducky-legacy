  .include "defs.asm"
main:
  li r0, 15
  li r1, 5
  sub r0, r1
  int $INT_HALT
