  .include "defs.asm"
main:
  li r0, 0xFFF0
  li r1, 0x000F
  or r0, r1
  int $INT_HALT
