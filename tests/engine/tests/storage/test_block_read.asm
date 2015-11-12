  .include "defs.asm"

  .data

  .type msg_block, int
  .int 0xFFFF

  .type redzone_pre, int
  .int 0xFEFE

  .type block, space
  .space $BLOCK_SIZE

  .type redzone_post, int
  .int 0xBFBF

  .text

main:
  li r0, 1
  li r1, $BLOCKIO_READ
  li r2, &msg_block
  lw r2, r2
  li r3, &block
  li r4, 1
  int $INT_BLOCKIO
  int $INT_HALT
