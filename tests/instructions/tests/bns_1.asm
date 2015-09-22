  .include "defs.asm"
main:
  li r0, 0x1FF
  cmp r0, 0xFF
  bns &label
  li r0, 0xEE
label:
  int $INT_HALT
