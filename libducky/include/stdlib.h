#ifndef	__DUCKY_STDLIB_H__
#define __DUCKY_STDLIB_H__

#include <types.h>

extern void *malloc(size_t len);
extern void free(void *ptr);
extern void *realloc(void *ptr, size_t len);

extern void malloc_init(void *heap, size_t len);

#endif // __DUCKY_STDLIB_H__
