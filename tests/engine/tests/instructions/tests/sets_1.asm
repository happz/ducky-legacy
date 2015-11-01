  .include "defs.asm"
main:
  li r0, 0xEE
  li r1, 0xFF
  li r2, 0xFF

  cmp r0, 0xFF
  sets r1

  cmp r0, 0xFF
  setns r2

  int $INT_HALT
