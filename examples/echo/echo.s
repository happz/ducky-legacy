.include "arch/ducky.hs"
.include "arch/keyboard.hs"
.include "arch/tty.hs"

  .data

  .type __interrupt_stack, space
  .space 64



  .text

main:
  ; setup interrupt handling
  li r0, 0x00                          ; EVT pointer
  la r1, &__interrupt_routine
  la r2, &__interrupt_stack
  add r2, 64

__evt_init:
  stw r0, r1
  add r0, $INT_SIZE
  stw r0, r2
  add r0, $INT_SIZE
  cmp r0, $PAGE_SIZE
  bne &__evt_init

__evt_done:
  sti                                  ; important: don't forget to enable interrupts

  li r1, 0x2A                          ; '*'

  li r2, $KBD_MMIO_ADDRESS
  add r2, $KBD_MMIO_DATA

  li r3, $TTY_MMIO_ADDRESS
  add r3, $TTY_MMIO_DATA

__echo_loop:
  lb r0, r2
  cmp r0, 0xFF
  be &__idle
  cmp r0, 0x71                         ; 'q'
  be &__exit

  stb r3, r1
  stb r3, r0
  stb r3, r1

  j &__echo_loop

__idle:
  idle
  j &__echo_loop

__exit:
  hlt 0x00

__interrupt_routine:
  retint

