  .data

  .type stack, space
  .space 64

  .type message, string
  .string "Hello, world!"

  .text

main:
  la sp, &stack
  add sp, 64

  la r0, &message
  call &writesn
  hlt 0x00
