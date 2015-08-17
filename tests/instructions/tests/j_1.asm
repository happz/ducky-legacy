main:
  li r0, 0xFF
  j &label
  li r0, 0xEE
label:
  int 0
