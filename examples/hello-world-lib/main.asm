  .type message, string
  .string "Hello, world!"

main:
  li r0, &message
  call &writesn
  li r0, 0
  int 0
