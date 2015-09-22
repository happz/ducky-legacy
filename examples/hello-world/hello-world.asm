  .type message, string
  .string "Hello, world!"

.include "defs.asm"

main:
  li r0, &message
  call &writesn
  li r0, 0
  int $INT_HALT

outb:
  ; > r0: port
  ; > r1: byte
  outb r0, r1
  ret

writesn:
  ; > r0: string address
  ; ...
  ;   r0: port
  ;   r1: current byte
  ;   r2: string ptr
  push r1
  push r2
  push r0
  pop r2
  li r0, $PORT_TTY_OUT
.__fn_writesn_loop:
  lb r1, r2
  bz &.__fn_writesn_write_nl
  call &outb
  inc r2
  j &.__fn_writesn_loop
.__fn_writesn_write_nl:
  ; \n
  li r1, 0xA
  call &outb
  ; \r
  li r1, 0xD
  call &outb
  li r0, 0
  pop r2
  pop r1
  ret

