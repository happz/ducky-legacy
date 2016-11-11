#include "forth.h"

u64_t do_DSUB(u64_t d1, u64_t d2)
{
  return d1 - d2;
}

i64_t do_DNEGATE(i64_t d)
{
  return 0 - d;
}

u64_t do_DADD(u64_t d1, u64_t d2)
{
  return d1 + d2;
}

u32_t do_DZEQ(i64_t d)
{
  return (d == 0 ? FORTH_TRUE : FORTH_FALSE);
}

u32_t do_DZLT(i64_t d)
{
  return (d < 0 ? FORTH_TRUE : FORTH_FALSE);
}

i64_t do_DTWOSTAR(i64_t d)
{
  return d << 1;
}

i64_t do_DTWOSLASH(i64_t d)
{
  return d >> 1;
}

u32_t do_DLT(i64_t d1, i64_t d2)
{
  return (d1 < d2 ? FORTH_TRUE : FORTH_FALSE);
}

u32_t do_DULT(u64_t d1, u64_t d2)
{
  return (d1 < d2 ? FORTH_TRUE : FORTH_FALSE);
}

u32_t do_DEQ(i64_t d1, i64_t d2)
{
  return (d1 == d2 ? FORTH_TRUE : FORTH_FALSE);
}

ASM_INT(cell_t, DODOES);

void do_TWOVARIABLE()
{
  counted_string_t *name = __read_word(' ');
  do_HEADER_COMMA(name);

  COMPILE(&DODOES);
  COMPILE(0);

  var_DP += 2;
}

i64_t do_DMAX(i64_t d1, i64_t d2)
{
  return (d1 > d2 ? d1 : d2);
}

i64_t do_DMIN(i64_t d1, i64_t d2)
{
  return (d1 < d2 ? d1 : d2);
}

i32_t do_DTOS(i64_t d)
{
  return (i32_t)d;
}

i64_t do_DABS(i64_t d)
{
  return (d < 0 ? -d : d);
}

i64_t do_MADD(i64_t d, i32_t n)
{
  return d + (i64_t)n;
}

i64_t do_MSTARSLASH(i64_t d, i32_t n1, i32_t n2)
{
//  d *= (i64_t)n1;
//  return d / (i64_t)n2;
  return d;
}
