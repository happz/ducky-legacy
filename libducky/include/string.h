#ifndef __DUCKY_STRING_H__
#define __DUCKY_STRING_H__

#include <types.h>

#ifndef __DUCKY_PURE_ASM__

extern void *memcpy(void *dst, const void *src, size_t n);
extern void *memset(void *dst, int c, size_t n);
extern int memcmp(const void *s1, const void *s2, size_t n);
extern void *memmove(void *dst, const void *src, size_t n);

extern size_t strlen(const char *s);
extern int strcmp(const char *s1, const char *s2);
extern int strncmp(const char *s1, const char *s2, size_t n);

extern char *strchr(const char *s, int c);

#endif // __DUCKY_PURE_ASM__

#endif
