  .include "ducky.asm"
  .include "keyboard.asm"
  .include "tty.asm"

  .data

  .type __interrupt_stack, space
  .space 64



  .text

main:
  ; setup interrupt handling
  li r0, 0x00                          ; IVT pointer
  la r1, &__interrupt_routine
  la r2, &__interrupt_stack
  add r2, 64

__ivt_init:
  stw r0, r1
  add r0, $INT_SIZE
  stw r0, r2
  add r0, $INT_SIZE
  cmp r0, $PAGE_SIZE
  bne &__ivt_init

__ivt_done:
  sti                                  ; important: don't forget to enable interrupts

  li r1, 0x2A                          ; '*'

__echo_loop:
  inb r0, $KBD_PORT_DATA
  cmp r0, 0xFF
  be &__idle
  cmp r0, 0x71                         ; 'q'
  be &__exit

  outb $TTY_PORT_DATA, r1
  outb $TTY_PORT_DATA, r0
  outb $TTY_PORT_DATA, r1

  j &__echo_loop

__idle:
  idle
  j &__echo_loop

__exit:
  hlt 0x00

__interrupt_routine:
  retint

