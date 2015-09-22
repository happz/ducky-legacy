  .include "defs.asm"
main:
  li r0, 0xFFFE
  li r1, 4
  add r0, r1
  int $INT_HALT
