  .include "defs.asm"
main:
  li r0, 2
  sub r0, 2
  int $INT_HALT
