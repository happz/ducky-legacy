#define CONIO_PORT_OUT  0x100
#define CONIO_PORT_ERR  0x101
#define STDOUT_FILENO   1
#define STDERR_FILENO   2

typedef unsigned char uint8_t;
typedef unsigned short uint16_t;

#ifdef DUCKYCC
extern void __asm__(char *, char *, ...);
#else
extern void __ducky_asm__(char *, char *, ...);
#define __asm__ __ducky_asm__
#endif

static void outb(uint16_t port, uint8_t b)
{
  __asm__("outb $0, $1", "r,r", port, b);
}

static void writeln(int fd, char *ptr, unsigned int len)
{
  int i;
  uint16_t port = CONIO_PORT_OUT;

  if (fd == STDERR_FILENO)
    port = CONIO_PORT_ERR;

  for(i = 0; i < len; i++)
    outb(port, ptr[i]);

  outb(port, 0xA);
  outb(port, 0xD);
}

int main(int argc, char **argv)
{
  writeln(STDOUT_FILENO, "Hello, world!", 13);

  return 0;
}

