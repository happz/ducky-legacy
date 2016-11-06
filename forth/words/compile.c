#include <forth.h>

ASM_INT(u32_t,   var_STATE);
ASM_INT(u32_t,   var_LATEST);
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

void do_HEADER_COMMA(counted_string_t *name)
{
#define CELL_ALIGN_DP() do { var_DP = (u32_t *)CELL_ALIGN((u32_t)var_DP); } while(0)

  word_header_t *header;

  // Start with cell-aligned DP
  CELL_ALIGN_DP();

  // Point header to the available space
  header = (word_header_t *)var_DP;

  // Point to the previous word
  header->wh_link = (word_header_t *)var_LATEST;

  // And update dictionary with our new word
  var_LATEST = (u32_t)var_DP;

  // Compute name CRC
  header->wh_name_crc = cs_crc(name);

  // Reset flags
  header->wh_flags = 0x00;

  // Copy name
  header->wh_name.cs_len = name->cs_len;
  __c_memcpy(&header->wh_name.cs_str, &name->cs_str, name->cs_len);

  // Extend DP to point right after the name
  // Subtract 1 - 1 char of the name is already member of
  // word_header_t's wh_name!
  var_DP = (u32_t *)((u32_t)var_DP + sizeof(word_header_t) + name->cs_len - 1);

  // Re-align DP once again - name could produce arbitrary alignment...
  CELL_ALIGN_DP();
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

ASM_STRUCT(counted_string_t, word_buffer_length);
ASM_INT(cell_t, COMMA);
ASM_INT(cell_t, LIT);

void do_POSTPONE()
{
  counted_string_t *wb = __read_dword_with_refill();

  if (!wb->cs_len) {
    // this should not happen...
     __ERR_unknown();
  }

  word_header_t *word;
  int found = fw_search(wb, &word);

  if (!found) {
    __ERR_undefined_word();
    return;
  }

  cf_t *cfa = do_TCFA(word);

  if (word->wh_flags & F_IMMED) {
    do_COMMA((u32_t)cfa);
  } else {
    do_COMMA((u32_t)&LIT);
    do_COMMA((u32_t)cfa);
    do_COMMA((u32_t)&COMMA);
  }
}
