  .include "defs.asm"
main:
  li r0, 10
  mod r0, 3
  int $INT_HALT
