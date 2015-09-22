  .include "defs.asm"
main:
  li r0, 0xFFF0
  or r0, 0x00F0
  int $INT_HALT
