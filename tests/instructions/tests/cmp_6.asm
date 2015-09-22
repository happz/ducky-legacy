  .include "defs.asm"
main:
  li r0, 1
  cmp r0, 0
  int $INT_HALT
