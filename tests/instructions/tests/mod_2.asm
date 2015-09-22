  .include "defs.asm"
main:
  li r0, 10
  mod r0, 1
  int $INT_HALT
