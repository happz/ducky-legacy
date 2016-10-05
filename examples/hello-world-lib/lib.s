#include "arch/tty.h"

  .global writesn

writesn:
  // > r0: string address
  // ...
  //   r0: port
  //   r1: current byte
  //   r2: string ptr
  push r1
  push r2
  mov r2, r0
  li r0, TTY_MMIO_ADDRESS
  add r0, TTY_MMIO_DATA
.__fn_writesn_loop:
  lb r1, r2
  bz .__fn_writesn_write_nl
  stb r0, r1
  inc r2
  j .__fn_writesn_loop
.__fn_writesn_write_nl:
  // \r
  li r1, 0xD
  stb r0, r1
  // \n
  li r1, 0xA
  stb r0, r1
  li r0, 0x00
  pop r2
  pop r1
  ret
