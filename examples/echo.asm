.def STDOUT_PORT: 0x100
.def STDIN_PORT:  0x100

main:
.__read_input:
  inb r0, $STDIN_PORT
  cmp r0, 0xFF
  be &.__wait_for_input
  outb $STDOUT_PORT, r0
  j &.__read_input

.__wait_for_input:
  idle
  j &.__read_input

