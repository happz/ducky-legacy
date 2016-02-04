.include "ducky.asm"
.include "svga.asm"


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
  call &writes

  li r0, $VGA_CMD_REFRESH
  outs $VGA_COMMAND_PORT, r0

  hlt 0x00


;
; void writes(char *s)
;
writes:
  push r1
  push r2
  push r3
  push r4

  ; attribute mask
  li r4, 0x0001
  shiftl r4, 15 ; blink
  or r4, 0x0400 ; red foreground

  li r3, $VGA_CMD_DEPTH
  outs $VGA_COMMAND_PORT, r3
  ins r3, $VGA_DATA_PORT

  li r2, 0xA000

.__writes_loop:
  lb r1, r0
  bz &.__writes_quit

  inc r0

  and r1, 0x007F ; leave just code point

  cmp r3, 1
  be &.__writes_1byte

  or r1, r4
  sts r2, r1
  add r2, 2
  j &.__writes_loop

.__writes_1byte:
  stb r2, r1
  inc r2
  j &.__writes_loop

.__writes_quit:
  pop r4
  pop r3
  pop r2
  pop r1
  ret
