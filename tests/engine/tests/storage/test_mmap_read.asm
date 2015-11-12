  .include "defs.asm"

.def MMAP_START: 0x8000
.def MSG_LENGTH: 64

  .data

  .type redzone_pre, int
  .int 0xFEFE

  .type buff, space
  .space $MSG_LENGTH

  .type redzone_post, int
  .int 0xBFBF

  .type msg_offset, int
  .int 0xFFFF

  .text

main:
  li r0, &msg_offset
  lw r0, r0
  add r0, $MMAP_START
  li r1, &buff
  li r2, $MSG_LENGTH
copy_loop:
  cmp r2, r2
  bz &quit
  lb r3, r0
  stb r1, r3
  inc r0
  inc r1
  dec r2
  j &copy_loop
quit:
  int $INT_HALT
