#include "forth.h"


ASM_INT(cell_t, LIT);
ASM_INT(cell_t, ZBRANCH);
ASM_INT(cell_t, BRANCH);


void do_AGAIN(u32_t *dest)
{
  COMPILE(&BRANCH);
  COMPILE((char *)dest - (char *)var_DP);
}

u32_t *do_BEGIN()
{
  return var_DP;
}

u32_t *do_ELSE(u32_t *ref1)
{
  u32_t *ref2;

  COMPILE(&BRANCH);

  ref2 = var_DP;

  COMPILE(0);

  *ref1 = (u32_t)((char *)var_DP - (char *)ref1);
  return ref2;
}

u32_t *do_IF()
{
  u32_t *ref;

  COMPILE(&ZBRANCH);
  ref = var_DP;
  COMPILE(0);

  return ref;
}

void do_REPEAT(u32_t *orig, u32_t *dest)
{
  COMPILE(&BRANCH);
  COMPILE((char *)dest - (char *)var_DP);

  *orig = (u32_t)((char *)var_DP - (char *)orig);
}

void do_THEN(u32_t *ref)
{
  *ref = (u32_t)((char *)var_DP - (char *)ref);
}

void do_UNTIL(u32_t *dest)
{
  COMPILE(&ZBRANCH);
  COMPILE((char *)dest - (char *)var_DP);
}

u32_t *do_WHILE()
{
  u32_t *ref;

  COMPILE(&ZBRANCH);
  ref = var_DP;
  COMPILE(0);

  return ref;
}
