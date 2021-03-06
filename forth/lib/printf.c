/*
 * The Minimal snprintf() implementation
 * Copyright (c) 2013 Michal Ludvig <michal@logix.cz>
 *
 * This is a minimal snprintf() implementation optimised
 * for embedded systems with a very limited program memory.
 * mini_snprintf() doesn't support _all_ the formatting
 * the glibc does but on the other hand is a lot smaller.
 * Here are some numbers from my STM32 project (.bin file size):
 *      no snprintf():      10768 bytes
 *      mini snprintf():    11420 bytes     (+  652 bytes)
 *      glibc snprintf():   34860 bytes     (+24092 bytes)
 * Wasting nearly 24kB of memory just for snprintf() on
 * a chip with 32kB flash is crazy. Use mini_snprintf() instead.
 */

#include <stdarg.h>

static unsigned int
mini_strlen(const char *s)
{
	unsigned int len = 0;
	while (s[len] != '\0') len++;
	return len;
}

static char *_putc(char ch, char *pbuffer, char *buffer, unsigned int buffer_len)
{
  if ((unsigned int)((pbuffer - buffer) + 1) >= buffer_len)
	  return 0;
  *(pbuffer++) = ch;
	*(pbuffer) = '\0';
  return pbuffer;
}

static char *_puts(char *s, unsigned int len, char *pbuffer, char *buffer, unsigned int buffer_len)
{
	unsigned int i;

	if (buffer_len - (pbuffer - buffer) - 1 < len)
		len = buffer_len - (pbuffer - buffer) - 1;

	/* Copy to buffer */
	for (i = 0; i < len; i++)
		*(pbuffer++) = s[i];
	*(pbuffer) = '\0';

  return pbuffer;
}

static unsigned int
mini_utoa(unsigned int value, unsigned int radix, unsigned int uppercase,
	 char *buffer, unsigned int zero_pad)
{
	char	*pbuffer = buffer;
	int	negative = 0;
	unsigned int	i, len;

	/* No support for unusual radixes. */
	if (radix > 16)
		return 0;

	/* This builds the string back to front ... */
	do {
		int digit = value % radix;
		*(pbuffer++) = (digit < 10 ? '0' + digit : (uppercase ? 'A' : 'a') + digit - 10);
		value /= radix;
	} while (value > 0);

	for (i = (pbuffer - buffer); i < zero_pad; i++)
		*(pbuffer++) = '0';

	if (negative)
		*(pbuffer++) = '-';

	*(pbuffer) = '\0';

	/* ... now we reverse it (could do it recursively but will
	 * conserve the stack space) */
	len = (pbuffer - buffer);
	for (i = 0; i < len / 2; i++) {
		char j = buffer[i];
		buffer[i] = buffer[len-i-1];
		buffer[len-i-1] = j;
	}

	return len;
}

int
mini_vsnprintf(char *buffer, unsigned int buffer_len, char *fmt, va_list va)
{
	char *pbuffer = buffer;
	char bf[24];
	char ch;

	while ((ch=*(fmt++))) {
		if ((unsigned int)((pbuffer - buffer) + 1) >= buffer_len)
			break;
		if (ch!='%')
			pbuffer = _putc(ch, pbuffer, buffer, buffer_len);
		else {
			char zero_pad = 0;
			char *ptr;
			unsigned int len;

			ch=*(fmt++);

			/* Zero padding requested */
			if (ch=='0') {
				ch=*(fmt++);
				if (ch == '\0')
					goto end;
				if (ch >= '0' && ch <= '9')
					zero_pad = ch - '0';
				ch=*(fmt++);
			}

			switch (ch) {
				case 0:
					goto end;

				case 'd': {
          int i = va_arg(va, int);
          unsigned int u = (unsigned int)(i >= 0 ? i : -i);

          if ((unsigned int)i != u)
            pbuffer = _putc('-', pbuffer, buffer, buffer_len);

					len = mini_utoa(u, 10, 0, bf, zero_pad);
					pbuffer = _puts(bf, len, pbuffer, buffer, buffer_len);
                  }
					break;

				case 'u':
          len = mini_utoa(va_arg(va, unsigned int), 10, 0, bf, zero_pad);
          pbuffer = _puts(bf, len, pbuffer, buffer, buffer_len);
          break;

				case 'x':
				case 'X':
					len = mini_utoa(va_arg(va, unsigned int), 16, (ch=='X'), bf, zero_pad);
					pbuffer = _puts(bf, len, pbuffer, buffer, buffer_len);
					break;

				case 'c' :
					pbuffer = _putc((char)(va_arg(va, int)), pbuffer, buffer, buffer_len);
					break;

				case 's' :
					ptr = va_arg(va, char*);
					pbuffer = _puts(ptr, mini_strlen(ptr), pbuffer, buffer, buffer_len);
					break;

        case 'C':
          ptr = va_arg(va, char *);
          len = va_arg(va, unsigned int);
          pbuffer = _puts(ptr, len, pbuffer, buffer, buffer_len);
          break;

				default:
					pbuffer = _putc(ch, pbuffer, buffer, buffer_len);
					break;
			}
		}
	}
end:
	return pbuffer - buffer;
}


int
mini_snprintf(char* buffer, unsigned int buffer_len, char *fmt, ...)
{
	int ret;
	va_list va;
	va_start(va, fmt);
	ret = mini_vsnprintf(buffer, buffer_len, fmt, va);
	va_end(va);

	return ret;
}
