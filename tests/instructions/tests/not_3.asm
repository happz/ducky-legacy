  .include "defs.asm"
main:
  li r0, 0xFFFF
  not r0
  int $INT_HALT
