  .include "defs.asm"
  .data

  .type foo, int
  .int 0xF00

  .text
main:
  li r0, &foo
  lw r1, r0
  li r2, 0xDEAD
  stw r0, r2
  int $INT_HALT
