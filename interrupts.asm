  .type jiffies, int
  .int 0

irq_timer:
  push r0
  push r1
  li r0, &jiffies
  lw r1, r0
  inc r1
  stw r0, r1
  pop r1
  pop r0
  retint

get_jiffies:
  push r1
  li r1, &jiffies
  lw r0, r1
  pop r1
  retint

int_halt:
  li r0, 0
  hlt r0

