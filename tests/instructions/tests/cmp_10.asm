  .include "defs.asm"
main:
  li r0, 20
  cmp r0, 10
  int $INT_HALT
