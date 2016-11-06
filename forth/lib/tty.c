#include <forth.h>
#include <arch/tty.h>

static char *tty_mmio_address = (char *)(CONFIG_TTY_MMIO_BASE + TTY_MMIO_DATA);


//-----------------------------------------------------------------------------
// Primitives for printing stuff to a TTY
// -----------------------------------------------------------------------------

void putc(char c)
{
  *tty_mmio_address = c;
}

void puts(char *s, u32_t len)
{
  while(len--)
    *tty_mmio_address = *s++;
}

void putcs(char *s)
{
  char c;

  while((c = *s++) != '\0')
    *tty_mmio_address = c;
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

char printf_buffer[CONFIG_PRINTF_BUFFER_SIZE] __attribute__((section(".bss")));

int printf(char *fmt, ...)
{
  int ret;
  va_list va;

  va_start(va, fmt);
  ret = mini_vsnprintf(printf_buffer, CONFIG_PRINTF_BUFFER_SIZE, fmt, va);
  va_end(va);

  puts(printf_buffer, ret);

  return ret;
}
