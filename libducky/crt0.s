//
// Entry point of every program
//

#include "arch/ducky.h"


  .section .bss.crt0.stack, "rwlb"
  .type _crt0_stack, space, PAGE_SIZE


  .section .text.crt0, "rxl"

_start:
  // setup a stack
  la sp, _crt0_stack
  add sp, PAGE_SIZE

  // reset FP to mark end of chain of frames
  li fp, 0x00

  // call main
  call main

  // and pass its return value as exit code
  hlt r0
