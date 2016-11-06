#include <types.h>
#include <forth.h>


int cs_cmp(counted_string_t *s1, counted_string_t *s2)
{
  if (s1->cs_len != s2->cs_len)
    return 1;

  if (s1->cs_len == 0)
    return 0;

  u8_t len = s1->cs_len;
  char *t1 = &s1->cs_str, *t2 = &s2->cs_str;

  while (len-- > 0)
    if (*t1++ != *t2++)
      return 1;

  return 0;
}

int __c_strcmp(char *s1, char *s2, u32_t len1, u32_t len2)
{
  if (len1 != len2)
    return 1;

  if (len1 == 0)
    return 0;

  while (len1-- > 0)
    if (*s1++ != *s2++)
      return 1;

  return 0;
}

void bzero(char *s, u32_t len)
{
  while(len-- > 0)
    *s++ = '\0';
}

void memset(u8_t *dst, u32_t c, u32_t len)
{
  DEBUG_printf("memset: dst=0x%08X, c=0x%02X, len=%u\r\n", (u32_t)dst, c, len);

  while(len-- > 0)
    *dst++ = c;
}

void __c_memcpy(char *dst, char *src, u32_t len)
{
  if (len == 0)
    return;

  while (len-- > 0)
    *dst++ = *src++;
}

ASM_INT(u32_t, var_DP);

void memmove(char *dst, char *src, u32_t len)
{
  if (len == 0)
    return;

  char *tmp = (char *)var_DP;

  __c_memcpy(tmp, src, len);
  __c_memcpy(dst, tmp, len);
}

u16_t strcrc(char *s, u8_t len)
{
  u32_t crc = 0;

  while(len-- > 0)
    crc += *s++;

  return crc;
}
