#include "forth.h"


DEFCONST("C/L", 3, 0x00, CHARS_PER_LINE, CONFIG_LIST_CPL)
DEFCONST("L/S", 3, 0x00, LINES_PER_SCREEN, CONFIG_LIST_LPS)

DEFCSTUB_01("BLK", 3, 0x00, BLK)
  // ( -- a-addr )


DEFCSTUB_11("BLOCK", 5, 0x00, BLOCK)
  // ( u -- a-addr )

DEFCSTUB_11("BUFFER", 6, 0x00, BUFFER)
  // ( u -- a-addr )

DEFCSTUB("EMPTY-BUFFERS", 13, 0x00, EMPTY_BUFFERS)
  // ( -- )

DEFCSTUB("FLUSH", 5, 0x00, FLUSH)
  // ( -- )

DEFCSTUB_10("LIST", 4, 0x00, LIST)
  // ( u -- )

DEFCSTUB_10("BLK-LOAD", 8, 0x00, BLK_LOAD)
  // ( u -- )

DEFWORD("LOAD", 4, 0x00, LOAD)
  // ( i*x u -- j*x )
  .word BLK_LOAD
  .word INTERPRET3
  .word BRANCH
  .word -8

DEFCSTUB_10("SAVE-BUFFER", 11, 0x00, SAVE_BUFFER)
  // ( u -- )

DEFCSTUB("SAVE-BUFFERS", 12, 0x00, SAVE_BUFFERS)
  // ( -- )

DEFVAR("SCR", 3, 0x00, SCR, 0x00000000)

DEFWORD("THRU", 4, 0x00, THRU)
  // ( i*x u1 u2 -- j*x )
  .word INCR
  .word SWAP
  .word TWODUP
  .word NEQU
  .word ZBRANCH
  .word 0x00000018
  .word PAREN_DO
  .word I
  .word LOAD
  .word PAREN_LOOP
  .word 0xFFFFFFF4
  .word EXIT


DEFCSTUB("UPDATE", 6, 0x00, UPDATE)
  // ( -- )
