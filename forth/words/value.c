#include "forth.h"

ASM_INT(u32_t, LIT);
ASM_INT(u32_t, TWOLIT);
ASM_INT(u32_t, STORE);
ASM_INT(u32_t, TWOSTORE);
ASM_INT(u32_t, SWAP);

#define is_VALUE(dfa)  (*(dfa) == (u32_t)&LIT)
#define is_2VALUE(dfa) (*(dfa) == (u32_t)&TWOLIT)

int do_TO(u32_t lo, u32_t hi)
{
  counted_string_t *name = __read_word(' ');

  word_header_t *word;
  if (!fw_search(name, &word)) {
    __ERR_undefined_word();
    return 0;
  }

  u32_t *dfa  = fw_data_field(word);
  u32_t *vfa = fw_value_field(word);

  if (IS_INTERPRET()) {
    if (is_VALUE(dfa)) {
      *vfa = hi;
      return 1;
    } else if (is_2VALUE(dfa)) {

      *vfa = lo;
      *(vfa + 1) = hi;
      return 2;
    }

    halt(0x69);

  } else {
    if (is_VALUE(dfa)) {
      COMPILE(&LIT);
      COMPILE(vfa);
      COMPILE(&STORE);
    } else if (is_2VALUE(dfa)) {
      COMPILE(&SWAP);
      COMPILE(&LIT);
      COMPILE(vfa);
      COMPILE(&TWOSTORE);
    } else {
      halt(0x71);
    }

    return 0;
  }
}

void do_VALUE(u32_t u)
{
  ASM_INT(cell_t, DOCOL);
  ASM_INT(cell_t, LIT);
  ASM_INT(cell_t, EXIT);

  counted_string_t *name = __read_word(' ');
  do_HEADER_COMMA(name);

  COMPILE(&DOCOL);
  COMPILE(&LIT);
  COMPILE(u);
  COMPILE(&EXIT);
}

void do_TWOVALUE(u32_t lo, u32_t hi)
{
  ASM_INT(cell_t, DOCOL);
  ASM_INT(cell_t, TWOLIT);
  ASM_INT(cell_t, EXIT);

  counted_string_t *name = __read_word(' ');
  do_HEADER_COMMA(name);

  COMPILE(&DOCOL);
  COMPILE(&TWOLIT);
  COMPILE(lo);
  COMPILE(hi);
  COMPILE(&EXIT);
}
