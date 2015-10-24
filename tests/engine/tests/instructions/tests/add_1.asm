  .include "defs.asm"
main:
  li r0, 5
  li r1, 10
  add r0, r1
  int $INT_HALT
