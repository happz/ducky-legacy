  .include "defs.asm"
  .text
main:
  li r1, 0xFF
  cli
  li r1, 0xEE
  int $INT_HALT
