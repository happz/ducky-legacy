  .include "defs.asm"
main:
  li r1, 0xFF
  li r2, 0xFF

  li r0, 0xFFFF
  add r0, 2
  seto r1

  li r0, 0xFFFF
  add r0, 2
  setno r2

  int $INT_HALT
