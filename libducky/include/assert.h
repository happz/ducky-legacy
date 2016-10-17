#ifndef __DUCKY_ASSERT_H__
#define __DUCKY_ASSERT_H__

#include <types.h>

#ifndef __DUCKY_PURE_ASM__

#define __ASSERT_VOID_CAST (void)

#ifdef NDEBUG
# define assert(expr)		(__ASSERT_VOID_CAST (0))
#else // !NDEBUG

extern void __assert_fail(const char *assertion, const char *file, unsigned int line, const char *function) __attribute__ ((__noreturn__));

# define assert(expr) \
  ((expr)             \
   ? __ASSERT_VOID_CAST(0)						\
   : __assert_fail(#expr, __FILE__, __LINE__, __PRETTY_FUNCTION__))

#endif // NDEBUG

#endif // __DUCKY_PURE_ASM__

#endif // __DUCKY_ASSERT_H__
