  .data

  .type stack, space
  .space 64

  .text

  li r0, 88
  la r1, &irq_routine
  stw r0, r1

  add r0, 4
  la r1, &stack
  add r1, 64
  stw r0, r1

  li r0, 0xFF
  li r1, 0xEE
  cmp r0, r0

  int 11

  hlt 0x00

irq_routine:
  ; modify some registers and flags
  li r1, 0xDD
  cmp r1, 0xFF
  retint
