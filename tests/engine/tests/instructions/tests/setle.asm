  .text

  li r0, 0xEE
  li r1, 0xFF
  li r2, 0xFF
  li r2, 0xFF

  cmp r0, 0xFF
  setle r1 ; 1

  cmp r0, 0xEE
  setle r2 ; 1

  cmp r0, 0xDD
  setl r3 ; 0

  hlt 0x00
