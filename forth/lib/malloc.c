/*
 * Support for allocating memory regions on heap.
 */

#include "forth.h"

typedef struct __attribute__((packed)) {
  u32_t h_length;  // Chunk size, including the header
} chunk_header_t;


ASM_PTR(u8_t *, var_HEAP);

void *malloc(u32_t size)
{
  u32_t actual_size = size + CELL;

  var_HEAP -= actual_size;
  var_HEAP = (u8_t *)((u32_t )var_HEAP & 0xFFFFFFFC);

  chunk_header_t *chunk = (chunk_header_t *)var_HEAP;
  chunk->h_length = actual_size;

#if CONFIG_MALLOC_REDZONE
  memset((void *)&chunk[1], 0x59, size);
#endif

  return &chunk[1];
}

void free(void *ptr)
{
#if CONFIG_MALLOC_REDZONE
  chunk_header_t *chunk = (chunk_header_t *)(ptr - sizeof(chunk_header_t));

  memset(chunk, 0x69, chunk->h_length);
#endif
}
