  .include "defs.asm"
main:
  li r0, 10
  li r1, 1
  mod r0, r1
  int $INT_HALT
