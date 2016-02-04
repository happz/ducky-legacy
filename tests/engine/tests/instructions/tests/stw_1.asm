  .data

  .type foo, int
  .int 0xDEADBEEF

  .text

  la r0, &foo
  lw r1, r0

  li r2, 0xADDE
  liu r2, 0xFD0C
  stw r0, r2
  hlt 0x00
