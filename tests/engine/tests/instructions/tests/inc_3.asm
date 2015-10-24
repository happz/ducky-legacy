  .include "defs.asm"
main:
  li r0, 0xFFFE
  inc r0
  int $INT_HALT
