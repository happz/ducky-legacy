  .include "defs.asm"
main:
  li r0, 2
  sub r0, 4
  int $INT_HALT
