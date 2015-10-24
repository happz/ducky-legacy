  .include "defs.asm"
main:
  li r0, 5
  mul r0, 3
  int $INT_HALT
