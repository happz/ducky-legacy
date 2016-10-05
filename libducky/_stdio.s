#include "arch/tty.h"

  .text

//
// void putc(int c)
//
// Writes one character to the terminal.
//
  .global putc
putc:
  li r1, TTY_MMIO_ADDRESS
  add r1, TTY_MMIO_DATA
  stb r1, r0
  ret


//
// void puts(const char *s)
//
// Writes string to the terminal, and adds a trailing newline.
//
  .global puts
puts:
  li r1, TTY_MMIO_ADDRESS
  add r1, TTY_MMIO_DATA

  lb r2, r0
__puts_loop:
  bz __puts_quit
  inc r0
  stb r1, r2
  lb r2, r0
  j __puts_loop
__puts_quit:
  li r2, 0xD
  stb r1, r2
  li r2, 0xA
  stb r1, r2
  ret
