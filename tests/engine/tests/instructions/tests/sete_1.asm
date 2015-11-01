  .include "defs.asm"
main:
  li r0, 0xFF
  li r1, 0xFF
  li r2, 0xFF
  cmp r0, r0
  sete r1
  cmp r0, r0
  setne r2
  int $INT_HALT
