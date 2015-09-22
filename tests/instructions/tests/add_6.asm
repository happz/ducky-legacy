  .include "defs.asm"
main:
  li r0, 0xFFFE
  add r0, 4
  int $INT_HALT
