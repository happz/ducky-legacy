  .include "defs.asm"
main:
  li r0, 0x00F0
  li r1, 0x0FF0
  xor r0, r1
  int $INT_HALT
