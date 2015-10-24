  .include "defs.asm"
main:
  li r0, 0
  shiftr r0, 2
  int $INT_HALT
