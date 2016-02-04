  .data

  .type redzone_pre, int
  .int 0xBFBFBFBF

  .type foo, int
  .int 0xDEADBEEF

  .type redzone_post, int
  .int 0xBFBFBFBF

  .text

  la r0, &foo
  add r0, 2
  ls r1, r0
  hlt 0x00
