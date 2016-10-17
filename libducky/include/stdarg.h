#ifndef __DUCKY_STDARG_H__
#define __DUCKY_STDARG_H__

#include <types.h>

#ifndef __DUCKY_PURE_ASM__

typedef __builtin_va_list   va_list;

#define va_start(ap, param) __builtin_va_start(ap, param)
#define va_end(ap)          __builtin_va_end(ap)
#define va_arg(ap, type)    __builtin_va_arg(ap, type)

#endif // __DUCKY_PURE_ASM__

#endif // __DUCKY_STDARG_H__
