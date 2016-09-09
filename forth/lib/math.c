#include <forth.h>

/*

static u32_t __mull_matrix[4][8];
static u32_t __mull_x[4];
static u32_t __mull_y[4];
static u32_t __mull_result[8];

static void __compact_orders(u32_t *row)
{
  int i;
  u32_t u;

  for(i = 7; i > 0; i--) {
    u = row[i];

    if (u <= 0xFFFF)
      continue;

    row[i - 1] += ((u & 0xFFFF0000) >> 16);
    row[i] &= 0xFFFF;
  }
}

static u64_t __mul64(u64_t x, u64_t y)
{
  __mull_x[3] = (x >> 48) & 0xFFFF, __mull_x[2] = (x >> 32) & 0xFFFF, __mull_x[1] = (x >> 16) & 0xFFFF, __mull_x[0] = x & 0xFFFF;
  __mull_y[3] = (y >> 48) & 0xFFFF, __mull_y[2] = (y >> 32) & 0xFFFF, __mull_y[1] = (y >> 16) & 0xFFFF, __mull_y[0] = y & 0xFFFF;

  int i;

  for(i = 0; i < 4; i++)
    __mull_matrix[0][4 + i] = __mull_y[3] * __mull_x[i];

  for(i = 0; i < 4; i++)
    __mull_matrix[1][3 + i] = __mull_y[2] * __mull_x[i];

  for(i = 0; i < 4; i++)
    __mull_matrix[2][4 + i] = __mull_y[1] * __mull_x[i];

  for(i = 0; i < 4; i++)
    __mull_matrix[1][4 + i] = __mull_y[0] * __mull_x[i];

  for(i = 0; i < 4; i++)
    __compact_orders(__mull_matrix[i]);

  for(i = 0; i < 8; i++)
    __mull_result[i] = __mull_matrix[0][i] + __mull_matrix[1][i] + __mull_matrix[2][i] + __mull_matrix[3][i];

  __compact_orders(__mull_result);

  return (__mull_result[4] << 48) | (__mull_result[5] << 32) | (__mull_result[6] << 16) | __mull_result[7];
}

static void __divmod64(u64_t X, u64_t Y, u64_t *Q, u64_t *R)
{
#define QUIT(_Q, _R) do { *Q = _Q; *R = _R; return; } while(0)

  if (X < Y)
    QUIT(0, X);

  if (X == Y)
    RETURN(1, 0);

  if (X == 0)
    QUIT(0, 0);

  if (Y == 0)
    halt(0x14);

  int i;
  u64_t q = 0, r = 0, nth_bit_mask = 0x800000000000;

  for(i = 63; i >= 0; i--, nth_bit_mask >> 1) {
    r <<= 1;
    r |= ((X & nth_bit_mask) >> i);

    if (r >= X) {
      r -= X;
      q |= nth_bit_mask;
    }
  }

  QUIT(q, r);

#undef QUIT
}


ASM_CALLABLE(u64_t do_STOD(u32_t u));
ASM_CALLABLE(u64_t do_MSTAR(u32_t u1, u32_t u2));


u64_t do_STOD(u32_t u)
{
  u64_t d = u;

  if (u & 0x80000000)
    d |= 0xFFFFFFFF00000000;

  return u;
}

u64_t do_MSTAR(u32_t u1, u32_t u2)
{
  return __mul64(u1, u2);
}
*/
