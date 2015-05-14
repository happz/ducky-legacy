int_routine_0:
  hlt r0

int_routine_10:
  ; modify some registers and flags
  li r0, 0xEE
  cmp r0, 0xFF
  retint

int_routine_11:
  ; disable interrupts
  cli
  hlt r0

int_routine_12:
  ; disable and enable interrupts
  cli
  sti
  hlt r0
