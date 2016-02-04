  .text

  li r0, 0xEE
  li r1, 0xFF
  li r2, 0xFF
  li r2, 0xFF

  cmp r0, 0xFF
  setl r1 ; 1

  cmp r0, 0xEE
  setl r2 ; 0

  cmp r0, 0xDD
  setl r3 ; 0

  hlt 0x00
