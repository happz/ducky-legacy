#ifndef __DUCKY_STDIO_H__
#define __DUCKY_STDIO_H__

#include <types.h>
#include <stdarg.h>

#ifndef __DUCKY_PURE_ASM__

extern void putc(int c);
extern void puts(const char *s);

int vsnprintf(char* buffer, u32_t n, char *fmt, va_list va);
int snprintf(char* buffer, u32_t n, char *fmt, ...);

void printf(char *fmt, ...);

#endif // !__DUCKY_PURE_ASM__

#define SEEK_SET  0
#define SEEK_CUR  1
#define SEEK_END  2

#endif // __DUCKY_STDIO_H__
