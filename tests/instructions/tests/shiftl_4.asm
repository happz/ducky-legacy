  .include "defs.asm"
main:
  li r0, 0
  shiftl r0, 2
  int $INT_HALT
