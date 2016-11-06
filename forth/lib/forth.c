#include <forth.h>

ASM_INT(u32_t,   var_LATEST);

int fw_search(counted_string_t *needle, word_header_t **found)
{
  *found = NULL;

  if (needle->cs_len == 0)
    return 0;

  if (var_LATEST == 0)
    return 0;

  u16_t needle_crc = cs_crc(needle);
  word_header_t *header = (word_header_t *)var_LATEST;

  for (; header != NULL; header = header->wh_link) {
    if (header->wh_flags & F_HIDDEN)
      continue;

    if (header->wh_name_crc != needle_crc)
      continue;

    if (cs_cmp(needle, &header->wh_name))
      continue;

    *found = header;
    return (header->wh_flags & F_IMMED ? 1 : -1);
  }

  return 0;
}

cf_t *fw_cfa(word_header_t *word)
{
  return (cf_t *)align4((u32_t)word + sizeof(word_header_t) - 1 + word->wh_name.cs_len);
}
