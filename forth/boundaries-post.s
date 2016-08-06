;
; Section boundary pivots
;
; This fiel must be the last one passed to the linker.
;

  .data
  .align 4
  .global __data_boundary_end
  .type __data_boundary_end, int
  .int 0xDEADBEEF

  .section .rodata
  .align 4
  .global __rodata_boundary_end
  .type __rodata_boundary_end, int
  .int 0xDEADBEEF


  .global __text_boundary_end
  .text
__text_boundary_end:
  ret
