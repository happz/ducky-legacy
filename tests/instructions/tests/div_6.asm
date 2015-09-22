  .include "defs.asm"
main:
  li r0, 10
  div r0, 20
  int $INT_HALT
