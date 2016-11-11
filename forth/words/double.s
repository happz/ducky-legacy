#include <forth.h>

#define DEFCSTUB_DOUBLE_1D1(name, len, flags, label)  \
  DEFCODE(name, len, flags, label)                    \
                                                      \
  pop r0                                              \
  mov r1, TOS                                         \
  call do_ ## label                                   \
  mov TOS, r0                                         \
  NEXT

#define DEFCSTUB_DOUBLE_1D1D(name, len, flags, label) \
  DEFCODE(name, len, flags, label)                    \
                                                      \
  pop r0                                              \
  mov r1, TOS                                         \
  call do_ ## label                                   \
  push r0                                             \
  mov TOS, r1                                         \
  NEXT

#define DEFCSTUB_DOUBLE_2D1D(name, len, flags, label) \
  DEFCODE(name, len, flags, label)                    \
                                                      \
  pop r2                                              \
  pop r1                                              \
  pop r0                                              \
  mov r3, TOS                                         \
  call do_ ## label                                   \
  push r0                                             \
  mov TOS, r1                                         \
  NEXT

#define DEFCSTUB_DOUBLE_2D1(name, len, flags, label)  \
  DEFCODE(name, len, flags, label)                    \
                                                      \
  pop r2                                              \
  pop r1                                              \
  pop r0                                              \
  mov r3, TOS                                         \
  call do_ ## label                                   \
  mov TOS, r0                                         \
  NEXT


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

DEFCODE("2ROT", 4, 0x00, TWOROT)
  // ( x1 x2 x3 x4 x5 x6 -- x3 x4 x5 x6 x1 x2 )
  pop r5
  pop r4
  pop r3
  pop r2
  pop r1
  push r3
  push r4
  push r5
  push TOS
  push r1
  mov TOS, r2
  NEXT

DEFCSTUB_20("2VALUE", 6, 0x00, TWOVALUE)
 // ( x1 x2 "<spaces>name" -- )

DEFCSTUB_DOUBLE_1D1("D0<", 3, 0x00, DZLT)
  // ( d -- flag )

DEFCSTUB_DOUBLE_1D1("D0=", 3, 0x00, DZEQ)
  // ( d -- flag )

DEFCSTUB_DOUBLE_2D1D("D+", 2, 0x00, DADD)
  // ( d1 d2 -- d3 )

DEFCSTUB_DOUBLE_2D1D("D-", 2, 0x00, DSUB)
  // ( d1 d2 -- d3 )

DEFCSTUB_DOUBLE_1D1D("DNEGATE", 7, 0x00, DNEGATE)
  // ( d1 -- d2 )

DEFCSTUB_DOUBLE_1D1D("D2*", 3, 0x00, DTWOSTAR)
  // ( d1 -- d2 )

DEFCSTUB_DOUBLE_1D1D("D2/", 3, 0x00, DTWOSLASH)
  // ( d1 -- d2 )

DEFCSTUB_DOUBLE_2D1("D<", 2, 0x00, DLT)
  // ( d1 d2 -- flag )

DEFCSTUB_DOUBLE_2D1("D=", 2, 0x00, DEQ)
  // ( d1 d2 -- flag )

DEFCSTUB_DOUBLE_2D1("DU<", 3, 0x00, DULT)
  // ( ud1 ud2 -- flag )

DEFCSTUB("2VARIABLE", 9, 0x00, TWOVARIABLE)
 // ( "<spaces>name" -- )

DEFCSTUB_DOUBLE_2D1D("DMAX", 4, 0x00, DMAX)
  // ( d1 d2 -- d3 )

DEFCSTUB_DOUBLE_2D1D("DMIN", 4, 0x00, DMIN)
  // ( d1 d2 -- d3 )

DEFCSTUB_DOUBLE_1D1("D>S", 3, 0x00, DTOS)
  // ( d -- n )

DEFCSTUB_DOUBLE_1D1D("DABS", 4, 0x00, DABS)
  // ( d -- d )

DEFCSTUB("M+", 2, 0x00, MADD)
  // ( d1 n -- d )
  pop r1
  pop r0
  mov r2, TOS
  call do_MADD
  push r0
  mov TOS, r1
  NEXT

DEFCSTUB("M*/", 3, 0x00, MSTARSLASH)
  // ( d1 n1 n2 -- d2 )
  pop r2
  pop r1
  pop r0
  mov r4, TOS
  call do_MSTARSLASH
  push r0
  mov TOS, r1
  NEXT

DEFCODE("D.", 2, 0x00, DDOT)
  // ( d -- )
  pop r0
  mov r1, TOS
  call print_i32
  call do_SPACE
  pop TOS
  NEXT

DEFCODE("D.R", 3, 0x00, DDOTR)
  // ( d -- )
  li X, 0x00                             // is N negative?
  pop r0                               // get N
  mov Y, r0                           // save N for later
  bns __DDOTR_unsigned
  li X, 1                             // yes, N is negative
  li r0, 0x00
  sub r0, Y                           // make it positive. positive is good.
__DDOTR_unsigned:
  call do_UWIDTH                       // find Ns width
  sub TOS, r0                         // how many spaces we need to print? may be negative, but SPACES dont care
  sub TOS, X                         // add one character for '-' sign
  swp TOS, r0
  call do_SPACES
  mov r0, Y
  call print_i32
  pop TOS
  NEXT
