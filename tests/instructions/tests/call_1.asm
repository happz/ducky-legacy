  .include "defs.asm"
main:
  li r0, 0xFF
  call &fn
  int $INT_HALT

fn:
  li r0, 0xEE
  ret
