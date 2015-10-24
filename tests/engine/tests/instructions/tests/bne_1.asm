  .include "defs.asm"
main:
  li r0, 0xFF
  cmp r0, 0xDD
  bne &label
  li r0, 0xEE
label:
  int $INT_HALT
