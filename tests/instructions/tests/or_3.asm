  .include "defs.asm"
main:
  li r0, 0xFFF0
  or r0, 0x000F
  int $INT_HALT
