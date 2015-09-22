  .include "defs.asm"
main:
  li r0, 15
  sub r0, 5
  int $INT_HALT
