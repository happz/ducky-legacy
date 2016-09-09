#include <forth.h>

ASM_INT(u32_t,   var_BASE);

/*
 * Find out the widht (in characters) of an unsigned number in the current base.
 *
 * ; ( u -- width )
 */
u32_t do_UWIDTH(u32_t u)
{
  u32_t len = 1;

  while(1) {
    u /= var_BASE;

    if (u == 0)
      return len;

    len++;
  }
}
