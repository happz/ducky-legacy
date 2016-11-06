/**
 * Implementation of ENVIRONMENT? word.
 *
 * Also, all environment queries are located in this file.
 */

#include <forth.h>

typedef struct {
  char label[32];
  u32_t label_len;

  environment_query_status_t (*handler)(environment_query_result_t *);
} environment_query_t;

#define __HEADER(_name) \
static environment_query_status_t __query_ ## _name (environment_query_result_t *result)

#define SUPPORTED(_name)               __HEADER(_name) { return TRUE; }
#define UNSUPPORTED(_name)             __HEADER(_name) { return FALSE; }
#define NUMBER(_name, _n)              __HEADER(_name) { result->number_lo = _n; return NUMBER; }
#define DOUBLE_NUMBER(_name, _lo, _hi) __HEADER(_name) { result->number_lo = _lo; result->number_hi = _hi; return DOUBLE_NUMBER; }

UNSUPPORTED(core);
UNSUPPORTED(core_ext);
UNSUPPORTED(memory_alloc);
UNSUPPORTED(memory_alloc_ext);
SUPPORTED(floored);

NUMBER(address_unit_bits, 8);

NUMBER(max_char, 127);
NUMBER(counted_string, STRING_SIZE);

NUMBER(rstack_cells, RSTACK_CELLS);
NUMBER(stack_cells, DSTACK_CELLS);

NUMBER(max_int, 0x7FFFFFFF);
NUMBER(max_int_unsigned, 0xFFFFFFFF);

DOUBLE_NUMBER(max_double, 0xFFFFFFFF, 0x7FFFFFFF);
DOUBLE_NUMBER(max_double_unsigned, 0xFFFFFFFF, 0xFFFFFFFF);

SUPPORTED(block);
SUPPORTED(block_ext);

#define QUERY(_name, _label, _len) { .label = _label, .label_len = _len, .handler = __query_ ## _name }

environment_query_t __queries[] __attribute__((section(".rodata"))) = {
  QUERY(counted_string, "/COUNTED-STRING", 15),
  QUERY(core, "CORE", 4),
  QUERY(core_ext, "CORE-EXT", 8),
  QUERY(floored, "FLOORED", 7),
  QUERY(max_char, "MAX-CHAR", 8),
  QUERY(rstack_cells, "RETURN-STACK-CELLS", 18),
  QUERY(stack_cells, "STACK-CELLS", 11),
  QUERY(address_unit_bits, "ADDRESS-UNIT-BITS", 17),
  QUERY(max_double, "MAX-D", 5),
  QUERY(max_double_unsigned, "MAX-UD", 6),
  QUERY(max_int, "MAX-N", 5),
  QUERY(max_int_unsigned, "MAX-U", 5),
  QUERY(memory_alloc, "MEMORY-ALLOC", 12),
  QUERY(memory_alloc_ext, "MEMORY-ALLOC-EXT", 16),
  QUERY(block,            "BLOCK", 5),
  QUERY(block_ext,        "BLOCK-EXT", 9)
};

#define NUM_QUERIES 17

environment_query_status_t do_ENVIRONMENT_QUERY(char *buff, u32_t len, environment_query_result_t *result)
{
  int i;

  for(i = 0; i < NUM_QUERIES; i++) {
    if (__c_strcmp(__queries[i].label, buff, __queries[i].label_len, len))
      continue;

    return __queries[i].handler(result);
  }

  return UNKNOWN;
}
