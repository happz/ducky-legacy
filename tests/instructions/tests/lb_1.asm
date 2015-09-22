  .include "defs.asm"
  .data

  .type redzone_pre, int
  .int 0xBFBF

  .type foo, int
  .int 0xDEAD

  .type redzone_post, int
  .int 0xBFBF

  .text
main:
  li r0, &foo
  lb r1, r0
  int $INT_HALT
