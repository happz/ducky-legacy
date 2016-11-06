#include <forth.h>


DEFWORD("2CONSTANT", 9, 0x00, TWOCONSTANT)
  .word DWORD
  .word HEADER_COMMA
  .word __DOCOL
  .word COMMA
  .word BRACKET_TICK
  .word TWOLIT
  .word COMMA
  .word SWAP
  .word COMMA
  .word COMMA
  .word BRACKET_TICK
  .word EXIT
  .word COMMA
  .word EXIT


DEFCODE("2LIT", 8, 0x00, TWOLIT)
  push TOS
  lw TOS, FIP
  add FIP, CELL
  push TOS
  lw TOS, FIP
  add FIP, CELL
  NEXT

DEFWORD("2LITERAL", 8, F_IMMED, TWOLITERAL)
  .word LIT
  .word TWOLIT
  .word COMMA
  .word SWAP
  .word COMMA
  .word COMMA
  .word EXIT

DEFCODE("DNEGATE", 7, 0x00, DNEGATE)
  // ( d1 -- d2 )
  li W, 0x00
  pop X
  sub W, X
  push W

  li W, 0x00
  sub W, TOS
  mov TOS, W
  NEXT
