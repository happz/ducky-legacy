  .data
buffer:
  .space 1024

main:
  li r0, 1
  li r1, 1024
  li r2, 0
  li r3, &buffer
  li r4, 1
  li r6, 1
  int r6
  li r0, &buffer
  call &writesn
  li r0, 0
  int r0

outb:
  # > r0: port
  # > r1: byte
  outb r0, r1
  ret

writesn:
  # > r0: string address
  # ...
  #   r0: port
  #   r1: current byte
  #   r2: string ptr
  push r1
  push r2
  push r0
  pop r2
  li r0, 0x100
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
  # \r
  li r1, 0xD
  call &outb
  li r0, 0
  pop r2
  pop r1
  ret

