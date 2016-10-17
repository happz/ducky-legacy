#ifndef	__DUCKY_SETJMP_H__
#define	__DUCKY_SETJMP_H__

#include <types.h>

#ifndef __DUCKY_PURE_ASM__

typedef u32_t jmp_buf[33]; // 32 registers + IP

extern int setjmp(jmp_buf);
extern void longjmp(jmp_buf, int) __attribute__((noreturn));

#endif // __DUCKY_PURE_ASM__

#endif // __DUCKY_SETJMP_H__
