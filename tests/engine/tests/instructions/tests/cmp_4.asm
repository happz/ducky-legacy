  .include "defs.asm"
main:
  li r0, 1
  cmp r0, 1
  int $INT_HALT
