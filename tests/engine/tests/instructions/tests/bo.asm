  .text

  li r0, 0xFFFF
  liu r0, 0xFFFF
  li r1, 0xFF
  add r0, 2
  bo &overflow
  li r1, 0xEE
  j &quit
overflow:
  li r1, 0xDD
quit:
  hlt 0x00
