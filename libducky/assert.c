#include <assert.h>
#include <stdio.h>

void __assert_fail(const char *assertion, const char *file, unsigned int line, const char *func)
{
  printf("Assertion '%s' failed, at file %s:%d, function %s\n", assertion, file, line, func);

  for(;;);
}
