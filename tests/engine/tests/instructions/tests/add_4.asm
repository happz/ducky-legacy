  .include "defs.asm"
main:
  li r0, 5
  add r0, 10
  int $INT_HALT
