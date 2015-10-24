  .include "defs.asm"
main:
  li r0, 0xFFFF
  inc r0
  int $INT_HALT
