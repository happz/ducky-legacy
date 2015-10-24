  .include "defs.asm"

  .data
  .type block, space
  .space $BLOCK_SIZE

main:
  li r0, 1
  li r1, $BLOCKIO_READ
  li r2, 16
  li r3, &block
  li r4, 1
  int $INT_BLOCKIO
  int $INT_HALT
