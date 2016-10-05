//
// Section boundary pivots
//
// This fiel must be the last one passed to the linker.
//

#include "forth.h"

  .data

  WORD(__data_boundary_end, 0xDEADBEEF)

  .section .rodata

  WORD(__rodata_boundary_end, 0xDEADBEEF)


  .global __text_boundary_end
  .text
__text_boundary_end:
  ret
