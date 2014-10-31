  .type message, string
  .string "Hello, world!"

main:
  loada r1, &message
  calli __fn_writesn_prolog
  hlt r0

__outb_prolog:
  # > r1: port
  # > r2: byte
  out r1, r2 b
  ret

__fn_writesn_prolog:
  # > r1: string address
  #   r2: current byte
  #   r3: port
  push r2
  push r3
  loada r3, 0x100
__fn_writesn_loop:
  load r2, r1 b
  jz __fn_writesn_write_nl
  push r1
  mov r1, r3
  calli __outb_prolog
  pop r1
  inc r1
  jmp __fn_writesn_loop
__fn_writesn_write_nl:
  push r1
  loada r1, 0x100
  # \n
  loada r2, 0xA b
  call __outb_prolog
  # \r
  loada r2, 0xD b
  call __outb_prolog
  pop r1
  loada r0, 0
  pop r3
  pop r2
  ret

