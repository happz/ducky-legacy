  .include "defs.asm"
main:
  li r0, 0x00F0
  shiftl r0, 4
  int $INT_HALT
