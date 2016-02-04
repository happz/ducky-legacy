  .data

  .type foo, int
  .int 0x0A

  .text

  la r1, &foo
  li r2, 0x0B
  li r3, 0x0C
  cas r1, r2, r3
  hlt 0x00
