  .include "defs.asm"

  .type message, string
  .string "Hello, world!"

main:
  li r0, &message
  call &writesn
  li r0, 0
  int $INT_HALT
