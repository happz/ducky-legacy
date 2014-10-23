data message, "Hello, world!"

main:
  loada r0, &message
  loada r1, 13
  call __fn_writeln_prolog
  hlt r0

__fn_writeln_prolog:
  # > r0: string address
  # > r1: string length
  #   r2: port
  #   r3: current byte
  push r2
  push r3
  loada r2, 0x100
__fn_writeln_loop:
  # string
  load r0, r3 b
  out r3, r2 b
  inc r0
  dec r1
  jnz __fn_writeln_loop
  # \n
  loada r3, 0xA b
  out r3, r2 b
  # \r
  loada r3, 0xD b
  out r3, r2 b
  pop r3
  pop r2
  loada r0, 0
  ret

