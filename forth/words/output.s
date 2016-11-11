#include "forth.h"

DEFCSTUB_20("AT-XY", 5, 0x00, AT_XY)
  // ( u1 u2 -- )

DEFCSTUB("PAGE", 4, 0x00, PAGE)
  // ( -- )
