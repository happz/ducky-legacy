/**
 * Implementation of common output-related words like CR or SPACE.
 *
 * If it's possible to place implementation to a different module,
 * e.g. in case of DOT and other number-printing words, their
 * definitions are located in a different module then. This one is
 * for those that are too generic or don't fit anywhere else.
 */

#include <forth.h>


void do_AT_XY(u32_t col, u32_t row)
{
  printf("\033[%d;%dH", row, col);
}


void do_PAGE()
{
  putcs("\033[2J;");
}


/*
 * Cause subsequent output to appear at the beginning of the next line.
 */
void do_CR()
{
  BR();
}


/*
 * Type content of input buffer delimited by right parenthesis.
 */
void do_DOT_PAREN()
{
  char c;

  do {
    c = __read_char();
    if (c == ')')
      break;
    putc(c);
  } while(1);
}


/*
 * Emit one space (0x20 in ASCII).
 */
void do_SPACE()
{
  putc(' ');
}


/*
 * Emit N spaces.
 *
 * When N is lower or equal to zero, no spaces will be printed.
 */
void do_SPACES(i32_t n)
{
  while(n-- > 0)
    putc(' ');
}
