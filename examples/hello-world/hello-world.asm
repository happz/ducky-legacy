.include "tty.asm"

  .data

  .type stack, space
  .space 64

  .type message, string
  .string "Hello, world!"


  .text

main:
  la sp, &stack
  add sp, 64

  la r0, &message
  call &writesn
  hlt 0x00


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
  mov r2, r0
  li r0, $TTY_PORT_DATA
.__writesn_loop:
  lb r1, r2
  bz &.__writesn_write_nl
  call &outb
  inc r2
  j &.__writesn_loop
.__writesn_write_nl:
  ; \n
  li r1, 0x0000000A
  call &outb
  ; \r
  li r1, 0x0000000D
  call &outb
  li r0, 0x00000000
  pop r2
  pop r1
  ret
