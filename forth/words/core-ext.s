/*
 * Core extension words (I couldn't place anywhere else :)
 */

#include "forth.h"

  .section .bss

  .type __pad_region, space, CONFIG_PAD_SIZE

DEFCODE("PAD", 3, 0x00, PAD)
  // ( -- c-addr )
  push TOS
  la TOS, __pad_region
  NEXT
