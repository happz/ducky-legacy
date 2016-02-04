  .text

  li r0, 0
  cmp r0, 0
  bz &label
  li r0, 0xEE
label:
  hlt 0x00
