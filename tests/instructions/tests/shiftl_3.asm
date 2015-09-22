  .include "defs.asm"
main:
  li r0, 0x8000
  shiftl r0, 1
  int $INT_HALT
