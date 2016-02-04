  .data

  .type foo, int
  .int 0xDEADBEEF

  .text

  la r0, &foo
  lw r1, r0
  hlt 0x00
