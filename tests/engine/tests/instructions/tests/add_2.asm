  .text

  li r0, 0xFFFE
  liu r0, 0xFFFF
  li r1, 2
  add r0, r1
  hlt 0x00
