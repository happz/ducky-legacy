  .include "defs.asm"
main:
  li r0, 0x00F0
  xor r0, 0x0FF0
  int $INT_HALT
