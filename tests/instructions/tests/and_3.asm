  .include "defs.asm"
main:
  li r0, 0xFFFF
  and r0, 0x0008
  int $INT_HALT
