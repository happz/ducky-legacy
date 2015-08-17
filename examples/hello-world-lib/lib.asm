  .global outb
outb:
  ; > r0: port
  ; > r1: byte
  outb r0, r1
  ret

  .global writesn
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
  li r0, 0x100
.__fn_writesn_loop:
  lb r1, r2
  bz &.__fn_writesn_write_nl
  call &outb
  inc r2
  j &.__fn_writesn_loop
.__fn_writesn_write_nl:
  ; \r
  li r1, 0xD
  call &outb
  ; \n
  li r1, 0xA
  call &outb
  li r0, 0
  pop r2
  pop r1
  ret

