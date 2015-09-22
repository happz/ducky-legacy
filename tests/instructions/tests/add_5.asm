  .include "defs.asm"
main:
  li r0, 0xFFFE
  add r0, 2
  int $INT_HALT
