main:
  li r0, 0xFF
  call &fn
  int 0

fn:
  li r0, 0xEE
  ret
