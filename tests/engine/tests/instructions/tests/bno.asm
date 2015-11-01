  .include "defs.asm"
main:
  li r0, 0x0000
  li r1, 0xFF

  add r0, 2
  bno &no_overflow
  li r1, 0xEE
  j &quit
no_overflow:
  li r1, 0xDD
quit:
  int $INT_HALT
