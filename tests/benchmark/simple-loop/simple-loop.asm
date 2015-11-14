.include "defs.asm"

.def L1_ITERS: 1000
.def L2_ITERS: 1000

  .data

  .type l1_iters, int
  .int $L1_ITERS

  .type l2_iters, int
  .int $L1_ITERS

  .text

main:
  li r2, 0
  li r0, &l1_iters
  lw r0, r0
  li r3, &l2_iters
  lw r3, r3
.l1_loop:
  bz &.l1_quit
  mov r1, r3
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
  int $INT_HALT
