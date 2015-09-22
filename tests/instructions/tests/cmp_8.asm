  .include "defs.asm"
main:
  li r0, 10
  cmp r0, 20
  int $INT_HALT
