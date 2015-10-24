  .include "defs.asm"
main:
  li r0, 0xFFF0
  not r0
  int $INT_HALT
