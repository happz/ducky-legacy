.def VGA_BUFF: 0xA000
.def VGA_COMMAND_PORT: 0x03F0
.def VGA_DATA_PORT: 0x03F1

.include "defs.asm"

  .type message, string
  .string "Hello, world!"

main:
  li r0, &message
  call &writes

  li r0, 0x0002
  out $VGA_COMMAND_PORT, r0
  out $VGA_COMMAND_PORT, r0

  li r0, 0
  int 0


writes:
  ; > r0: string address

  push r1
  push r2
  push r3

  li r3, 0x0023
  out $VGA_COMMAND_PORT, r3
  in r3, $VGA_DATA_PORT

  li r2, $VGA_BUFF

.__writes_loop:
  lb r1, r0
  bz &.__writes_quit

  inc r0

  and r1, 0x007F ; leave just code point

  cmp r3, 1
  be &.__writes_1byte

  or r1, 0x0400  ; set fg to red
  or r1, 0x8000  ; set blink on
  stw r2, r1
  add r2, 2
  j &.__writes_loop

.__writes_1byte:
  stb r2, r1
  inc r2
  j &.__writes_loop

.__writes_quit:
  pop r3
  pop r2
  pop r1
  ret
