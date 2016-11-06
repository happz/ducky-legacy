#include <forth.h>

ASM_INT(u32_t,   var_BASE);

u8_t pno_buffer[CONFIG_PNO_BUFFER_SIZE];
u8_t *pno_ptr = NULL;
char pno_chars[] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";


void pno_reset_buffer()
{
  memset(pno_buffer, 0xBF, CONFIG_PNO_BUFFER_SIZE);
  pno_ptr = (u8_t *)(pno_buffer + CONFIG_PNO_BUFFER_SIZE);
}

void pno_add_char(u8_t c)
{
  *--pno_ptr = c;
}

void pno_add_number(int i)
{
  pno_add_char(pno_chars[i]);
}

void do_HOLDS(u8_t *s, u32_t len)
{
  u8_t *t = pno_ptr - len;
  pno_ptr = t;

  while(len--)
    *t++ = *s++;
}

int do_ISNUMBER(counted_string_t *needle, i32_t *num)
{
  DEBUG_printf("do_ISNUMBER: needle='%C'\r\n", &needle->cs_str, (unsigned int)needle->cs_len);

  parse_number_result_t pnr;

  int ret = parse_number(needle, &pnr);

  DEBUG_printf("do_ISNUMBER: ret=%d, remaining=%d, number_lo=%d, number_hi=%d\r\n", ret, pnr.nr_remaining, pnr.nr_number_lo, pnr.nr_number_hi);

  if (ret == -1 || pnr.nr_remaining != 0)
    return FORTH_FALSE;

  *num = pnr.nr_number_lo;
  return FORTH_TRUE;
}


void do_LESSNUMBERSIGN()
{
  pno_reset_buffer();
}


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
