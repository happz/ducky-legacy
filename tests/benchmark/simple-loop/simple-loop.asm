.include "defs.asm"

.def L1_ITERS: 1000
.def L2_ITERS: 5000


loop:
  li r2, 0
  li r0, $L1_ITERS
.l1_loop:
  bz &.l1_quit
  li r1, $L2_ITERS
.l2_loop:
  bz &.l2_quit
  inc r2
  dec r2
  dec r1
  j &.l2_loop
.l2_quit:
  dec r0
  j &.l1_loop
.l1_quit:
  ret

main:
  call &loop
  int $INT_HALT
