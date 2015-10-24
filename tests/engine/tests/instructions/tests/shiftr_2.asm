  .include "defs.asm"
main:
  li r0, 16
  shiftr r0, 4
  int $INT_HALT
