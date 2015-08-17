  .text
main:
  li r1, 0xFF
  cli
  li r1, 0xEE
  int 0
