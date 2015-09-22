  .include "defs.asm"
main:
  li r0, 1
  shiftl r0, 4
  int $INT_HALT
