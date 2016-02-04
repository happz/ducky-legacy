  .data

  .type message, string
  .string "Hello, world!"

  .text

main:
  la r0, &message
  call &writesn
  hlt 0x00
