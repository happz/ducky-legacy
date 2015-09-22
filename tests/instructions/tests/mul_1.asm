  .include "defs.asm"
main:
  li r0, 5
  li r1, 3
  mul r0, r1
  int $INT_HALT
