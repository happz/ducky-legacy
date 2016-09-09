#include <forth.h>

ASM_INT(u32_t,   var_STATE);
ASM_PTR(u32_t *, var_DP);


#define FWD_DP(_len) do { var_DP = (u32_t *) CELL_ALIGN((u32_t)var_DP + (_len)); } while(0)


/*
 * Store argument into a userspace cell pointed to by DP. DP is increased
 * by a width of a cell/word.
 *
 * :param u: word to store into memory.
 */
void do_COMMA(u32_t u)
{
  *var_DP++ = u;
}


/*
 * `S"` and `C"` implementation. Words are simple wrappers for this
 * function.
 */
void do_LITSTRING(cf_t *cfa)
{
  if (var_STATE == 0)
    __ERR_no_interpretation_semantics();

  do_COMMA((u32_t)cfa);

  counted_string_t *payload = (counted_string_t *)var_DP;

  payload->cs_len = 0;
  char *buff = &payload->cs_str, c;

  while((c = __read_char()) != '"')
    buff[payload->cs_len++] = c;

  FWD_DP(payload->cs_len + 1);
}
