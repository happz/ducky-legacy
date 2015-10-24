  .include "defs.asm"
main:
  li r0, 0xFF
  j &label
  li r0, 0xEE
label:
  int $INT_HALT
