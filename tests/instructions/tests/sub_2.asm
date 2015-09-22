  .include "defs.asm"
main:
  li r0, 2
  li r1, 2
  sub r0, r1
  int $INT_HALT
