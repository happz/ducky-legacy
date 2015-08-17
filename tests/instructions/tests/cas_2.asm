  .data

  .type foo, int
  .int 0x0A

  .text
main:
  li r1, &foo
  li r2, 0x0B
  li r3, 0x0C
  cas r1, r2, r3
  int 0
