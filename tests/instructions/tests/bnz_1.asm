main:
  li r0, 0xFF
  cmp r0, 0
  bnz &label
  li r0, 0xEE
label:
  int 0