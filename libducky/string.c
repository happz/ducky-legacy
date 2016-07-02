#include <types.h>

void memcpy(void *dst, const void *src, u32_t n)
{
  u8_t *d = (u8_t *)dst, *s = (u8_t *)src, c;

  while(n-- > 0)
    *d++ = *s++;
}

void memset(void *dst, u8_t c, u32_t n)
{
  u8_t *d = (u8_t *)dst;

  while(n-- > 0)
    *d++ = c;
}
