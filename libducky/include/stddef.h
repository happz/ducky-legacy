#ifndef __DUCKY_STDDEF_H__
#define __DUCKY_STDDEF_H__

#ifndef __DUCKY_PURE_ASM__

# define NULL ((void*)0)

#endif // ! __DUCKY_PURE_ASM__

#define offsetof(t, d) __builtin_offsetof(t, d)

#endif // __DUCKY_STDDEF_H__
