  .include "defs.asm"
main:
  li r0, 1
  dec r0
  int $INT_HALT
