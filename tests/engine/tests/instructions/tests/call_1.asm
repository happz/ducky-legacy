  .data

  .type stack, space
  .space 64

  .text

  la sp, &stack
  add sp, 64

  li r0, 0xFF
  call &fn
  hlt 0x00

fn:
  li r0, 0xEE
  ret
