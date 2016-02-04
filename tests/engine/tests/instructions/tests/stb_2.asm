  .data

  .type foo, int
  .int 0x0

  .text

  la r0, &foo
  inc r0
  lw r1, r0
  li r2, 0xDE
  stb r0, r2
  hlt 0x00
