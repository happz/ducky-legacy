#include <forth.h>

ASM_INT(u32_t, var_BASE);

/*
 * Parse string S, and try to convert it to an integer. Returns 0 on success,
 * or 1 on success when the result is a double-cell integer, -1 otherwise.
 */
int parse_number(counted_string_t *s, parse_number_result_t *result)
{
#define error()         do { result->nr_remaining = len; return -1; } while(0);
#define quit(_ret)      do { result->nr_number_lo = i; result->nr_remaining = len; return _ret; } while(0);
#define getch()         do { c = *t++; len--; } while(0)
#define getch_checked() do { if (!len) error(); c = *t++; len--; } while(0)

  u8_t len = s->cs_len;

  // Let's say an empty string is wrong...
  if (!len)
    error();

  char c, *t = &s->cs_str;
  int base = 0;
  i32_t i = 0;

  // Reset high cell - no large strings, suppose anything we can parse fits
  // into a single cell.
  result->nr_number_hi = 0;

  // check whether the first char is a base-denoting prefix
  getch();

  switch(c) {
    case '#':
    case '&':
      base = 10;
      break;
    case '$':
      base = 16;
      break;
    case '%':
      base = 2;
      break;

    // this one is special - the number is ASCII code of the char after '
    case '\'':
      getch_checked();

      i = (int)c;

      // if there's no trailing char, it's all good
      if (!len)
        quit(0);

      // if there is trailing char, it must be '
      getch();

      if (c == '\'')
        quit(0);

    default:
      // we'll set base in the next step
      break;
  }

  if (base == 0) {
    // no base prefix, use the default one
    base = var_BASE;
  } else {
    // get next char
    getch_checked();
  }

  // ok, now we know the base, and we have a character to process
  int negative = 0;

  if (c == '-') {
    negative = 1;
    getch_checked();
  }

  // now it's time to parse the rest of characters
  do {
    // if the char is dot, it denotes double cell
    // it is also the last - whatever characters are behind
    // this one, it *is* the last one...
    if (c == '.') {
      if (negative) {
        i *= -1;

        // don't forget to flip the upper cell as well
        result->nr_number_hi = 0xFFFFFFFF;
      }

      quit(1);
    }

    // c cannot be bellow '0', the first digit in ASCII table
    if (c < '0')
      error();

    // if it's lower case, convert it to upper case
    if (c >= 'a' && c <= 'z')
      c -= 32;

    // if it's between numbers and letters, it's nonsense
    if (c > '9' && c < 'A')
      error();

    // remove that gap between numbers and letters
    if (c >= 'A')
      c -= ('A' - '9') - 1;

    // subtract everything up to '0'
    c -= '0';

    // if the digit cannot fit in the base, that's very bad...
    if (c >= base)
      error();

    i *= base;
    i += (int)c;

    if (!len)
      break;

    getch();
  } while(1);

  if (negative)
    i *= -1;

  quit(0);
}


// Using buffer to avoid recursion - I just put all chars in the buff,
// and then print them in reversed order. And 64 is maximal length of
// any number in most verbose base, 2, plus one for '-'.
static char __number_fmt_buffer[65];

static void __print_number_buffer(int index)
{
  /* TODO: this is way too complicated, but for unknown reason
   * llvm creates something that simply does not work as expected
   * for a shorter C code:
   *
   * while(i >= 0)
   *   putc(__number_fmt_buffer[i--]);
   */
  while(1) {
    putc(__number_fmt_buffer[index--]);

    if (index == -1)
      break;
  }
}

static int __format_u32(u32_t u)
{
  int i = 0;
  u32_t r, base = (u32_t)var_BASE;

  do {
    r = u % base;

    __number_fmt_buffer[i++] = (r < 10 ? (r + 48) : (r - 10 + 65));

    u /= base;
  } while(u != 0);

  return i - 1;
}

void print_i32(i32_t i)
{
  if (i & 0x80000000) {
    putc('-');

    i = 0 - i;
  }

  __print_number_buffer(__format_u32((u32_t)i));
}

void print_u32(u32_t u)
{
  __print_number_buffer(__format_u32(u));
}
