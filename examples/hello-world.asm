  .type message, string
  .string "Hello, world!"

main:
  li r1, &message
  calli @__fn_writesn_prolog
  hlt r0

__outb_prolog:
  # > r1: port
  # > r2: byte
  outb r1, r2 b
  ret

__fn_writesn_prolog:
  # > r1: string address
  #   r2: current byte
  #   r3: port
  push r2
  push r3
  li r3, 0x100
__fn_writesn_loop:
  lb r2, r1
  bz @__fn_writesn_write_nl
  push r1
  mov r1, r3
  calli @__outb_prolog
  pop r1
  inc r1
  j @__fn_writesn_loop
__fn_writesn_write_nl:
  push r1
  li r1, 0x100
  # \n
  li r2, 0xA
  calli @__outb_prolog
  # \r
  li r2, 0xD
  calli @__outb_prolog
  pop r1
  li r0, 0
  pop r3
  pop r2
  ret

