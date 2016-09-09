#include <forth.h>

ASM_PTR(char *, tty_mmio_address);


//-----------------------------------------------------------------------------
// Primitives for printing stuff to a TTY
// -----------------------------------------------------------------------------

void putc(char c)
{
  *tty_mmio_address = c;
}

void puts(char *s, u32_t len)
{
  char *tty = tty_mmio_address;

  while(len--)
    *tty = *s++;
}

void putcs(char *s)
{
  char *tty = tty_mmio_address, c;

  while((c = *s++) != '\0')
    *tty = c;
}

void putnl()
{
  putc('\r'); putc('\n');
}


//-----------------------------------------------------------------------------
// Prompt
//-----------------------------------------------------------------------------

static char default_prompt[] = " ok\r\n";

void do_print_prompt()
{
  putcs(default_prompt);
}

void print_prompt(u32_t enabled)
{
  if (enabled != FORTH_TRUE)
    return;

  do_print_prompt();
}


//-----------------------------------------------------------------------------
// Formatting output
//-----------------------------------------------------------------------------

static char __hex_digits[] = "0123456789ABCDEF";

void print_hex(u32_t u)
{
  putc('0'); putc('x');

  int i;
  u32_t v;

  for(i = 0; i < 8; i++) {
    v = (u >> (28 - (i * 4))) & 0x0000000F;
    putc(__hex_digits[v]);
  }
}
