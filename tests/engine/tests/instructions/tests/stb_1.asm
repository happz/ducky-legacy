  .data

  .type foo, int
  .int 0x0

  .text

  la r0, &foo
  lw r1, r0
  li r2, 0xDEAD
  liu r2, 0xBEEF
  stb r0, r2
  hlt 0x00
