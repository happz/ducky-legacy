  .include "defs.asm"
main:
  li r0, 10
  mod r0, 2
  int $INT_HALT
