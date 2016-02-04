  .data

  .type foo, int
  .int 0x0

  .text

  la r0, &foo
  add r0, 2
  lw r1, r0
  li r2, 0xDEAD
  sts r0, r2
  hlt 0x00
