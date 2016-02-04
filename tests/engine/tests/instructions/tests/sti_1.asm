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

  int 11

irq_routine:
  ; disable and enable interrupts
  cli
  sti
  hlt 0x00
