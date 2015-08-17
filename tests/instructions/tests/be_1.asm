main:
  li r0, 0xFF
  cmp r0, r0
  be &label
  li r0, 0xEE
label:
  int 0
