#include <stdint.h>
#include <string.h>
#include <stddef.h>

void *memcpy(void *dst, const void *src, size_t n)
{
  if (!(((uptr_t)dst) & 3) && !(((uptr_t)src) & 3)) {
    // pointers are word-aligned
    u32_t *d = dst;
    const u32_t *s = src;

    // copy words
    for (size_t i = (n >> 2); i; i--)
      *d++ = *s++;

    // copy short
    if (n & 2) {
      *(u16_t *)d = *(const u16_t *)s;
      d = (u32_t *)((u16_t *)d + 1);
      s = (const u32_t *)((const u16_t *)s + 1);
    }

    // copy remaining byte
    if (n & 1)
      *((u8_t *)d) = *((const u8_t *)s);

  } else {
    // unaligned access, do it the hard way
    u8_t *d = dst;
    const u8_t *s = src;

    for(; n; n--)
      *d++ = *s++;
  }

  return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
  if (src < dst && (u8_t*)dst < (const u8_t *)src + n) {
    u8_t *d = (u8_t *)dst + n - 1;
    const u8_t *s = (const u8_t*)src + n - 1;

    for (; n > 0; n--)
      *d-- = *s--;

    return dst;
  }

  return memcpy(dst, src, n);
}

void *memset(void *s, int c, size_t n)
{
  if (c == 0 && ((uptr_t)s & 3) == 0) {
    u32_t *s32 = s;

    for (size_t i = n >> 2; i > 0; i--)
      *s32++ = 0;

    if (n & 2) {
      *((u16_t *)s32) = 0;
      s32 = (u32_t *)((u16_t *)s32 + 1);
    }

    if (n & 1)
      *((u8_t *)s32) = 0;
  } else {
    u8_t *s2 = s;

    for (; n > 0; n--)
      *s2++ = c;

  }

  return s;
}

int memcmp(const void *s1, const void *s2, size_t n)
{
  const u8_t *s1_8 = s1;
  const u8_t *s2_8 = s2;

  while (n--) {
    char c1 = *s1_8++;
    char c2 = *s2_8++;

    if (c1 < c2)
      return -1;

    if (c1 > c2)
      return 1;
  }

  return 0;
}

void *memchr(const void *s, int c, size_t n)
{
  if (n != 0) {
    const u8_t *p = s;

    do {
      if (*p++ == c)
        return ((void *)(p - 1));
    } while (--n != 0);
  }

  return 0;
}

size_t strlen(const char *str)
{
  size_t len = 0;

  for (const char *s = str; *s; s++)
    len++;

  return len;
}

int strcmp(const char *s1, const char *s2)
{
  while (*s1 && *s2) {
    char c1 = *s1++;
    char c2 = *s2++;

    if (c1 < c2)
      return -1;

    if (c1 > c2)
      return 1;
  }

  if (*s2)
    return -1;

  if (*s1)
    return 1;

  return 0;
}

int strncmp(const char *s1, const char *s2, size_t n)
{
  while (*s1 && *s2 && n > 0) {
    char c1 = *s1++;
    char c2 = *s2++;

    n--;

    if (c1 < c2)
      return -1;

    if (c1 > c2)
      return 1;
  }

  if (n == 0)
    return 0;

  if (*s2)
    return -1;

  if (*s1)
    return 1;

  return 0;
}

char *strcpy(char *dst, const char *src)
{
  while (*src)
    *dst++ = *src++;

  *dst = '\0';
  return dst;
}

char *strcat(char *dst, const char *src)
{
  while (*dst)
    dst++;

  while (*src)
    *dst++ = *src++;

  *dst = '\0';

  return dst;
}

char *strchr(const char *s, int c)
{
  while (*s != '\0' && *s != (char)c)
    s++;

  return ((*s == c) ? (char *)s : NULL);
}

char *strstr(const char *haystack, const char *needle)
{
  size_t needlelen;

  if (*needle == '\0')
    return (char *)haystack;

  needlelen = strlen(needle);

  for (; (haystack = strchr(haystack, *needle)) != 0; haystack++)
    if (strncmp(haystack, needle, needlelen) == 0)
      return (char *) haystack;

  return NULL;
}
