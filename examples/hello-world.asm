data message, "Hello, world!"

main:
  loada r1, &message
  loada r2, 13
  call __fn_writeln_prolog
  hlt r0

__outb_prolog:
  # > r1: port
  # > r2: byte
  out r1, r2 b
  ret

__fn_writeln_prolog:
  # > r1: string address
  # > r2: string length
  #   r3: current byte
  #   r4: port
  push r3
  push r4
  loada r4, 0x100
__fn_writeln_loop:
  load r3, r1 b
  push r1
  push r4
  pop r1
  push r2
  push r3
  pop r2
  call __outb_prolog
  pop r2
  pop r1
  inc r1
  dec r2
  jnz __fn_writeln_loop
  push r1
  push r4
  pop r1
  # \n
  loada r2, 0xA b
  call __outb_prolog
  loada r2, 0xD b
  call __outb_prolog
  pop r1
  loada r0, 0
  pop r4
  pop r3
  ret

