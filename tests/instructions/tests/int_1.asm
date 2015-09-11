main:
  li r0, 0xFF
  li r1, 0xEE
  cmp r0, r0
  int 10
  int 0
