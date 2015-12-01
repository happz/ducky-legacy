.include "defs.asm"

irq_routine_$INT_HALT:
  hlt r0

irq_routine_10:
  ; modify some registers and flags
  li r1, 0xDD
  cmp r1, 0xFF
  retint

irq_routine_11:
  ; disable interrupts
  cli
  hlt r0

irq_routine_12:
  ; disable and enable interrupts
  cli
  sti
  hlt r0
