  .include "defs.asm"
main:
  li r0, 2
  shiftr r0, 1
  int $INT_HALT
