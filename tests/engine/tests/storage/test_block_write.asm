  .include "defs.asm"

  .data

  .type msg_block, int
  .int 0xFFFF

  .type block, space
  .space $BLOCK_SIZE

  .text

main:
  li r0, 1
  li r1, $BLOCKIO_WRITE
  li r2, &block
  li r3, &msg_block
  lw r3, r3
  li r4, 1
  int $INT_BLOCKIO
  int $INT_HALT
