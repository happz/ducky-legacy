  .include "defs.asm"
main:
  li r0, 0x0
  not r0
  int $INT_HALT
