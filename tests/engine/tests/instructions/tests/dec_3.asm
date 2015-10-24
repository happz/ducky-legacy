  .include "defs.asm"
main:
  li r0, 2
  dec r0
  int $INT_HALT
