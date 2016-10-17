#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#include <arch/ducky.h>
#include <arch/tty.h>


//-----------------------------------------------------------------------------
// Printing stuff
//-----------------------------------------------------------------------------

static volatile u8_t *tty_mmio_address = (u8_t *)(TTY_MMIO_ADDRESS + TTY_MMIO_DATA);


/*
 * void putc(int c)
 *
 * Writes one character to the terminal.
 */
void putc(int c)
{
  *tty_mmio_address = (char)c;
}


/*
 * void puts(const char *s)
 *
 * Writes string to the terminal.
 */
void puts(const char *s)
{
  char c;

  while ((c = *s++) != '\0')
    *tty_mmio_address = c;
}
