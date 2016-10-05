//
// Simple loopy benchmark. Not very sophisticated but simple and quite reloable.
//

#define L1_ITERS 1000
#define L2_ITERS 1000

  .data

  .type l1_iters, word, L1_ITERS
  .type l2_iters, word, L2_ITERS


  .text

  li r2, 0x00
  la r0, l1_iters
  lw r0, r0
  la r3, l2_iters
  lw r3, r3
.l1_loop:
  bz .l1_quit
  mov r1, r3
.l2_loop:
  bz .l2_quit
  add r2, 8
  sub r2, 8
  dec r1
  j .l2_loop
.l2_quit:
  dec r0
  j .l1_loop
.l1_quit:
  hlt 0x00
