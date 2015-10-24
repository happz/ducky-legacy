  .include "defs.asm"
  .data
  .type foo, int
  .int 0xDEAD

  .text
main:
  li r0, &foo
  lw r1, r0
  int $INT_HALT
