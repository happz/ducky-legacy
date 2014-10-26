#define CONIO_OUT_PORT  0x100
#define STDOUT_FD       0

typedef unsigned char uint8_t;
typedef unsigned short uint16_t;

static void outb(uint16_t port, uint8_t b)
{
  __asm__("out $0, $1 b", port, b);
}

static void writeln(int fd, unsigned char *ptr, unsigned int len)
{
  int i;
  uint16_t port = CONIO_OUT_PORT;

  for(i = 0; i < len; i++)
    outb(port, ptr[i]);

  outb(port, 0xA);
  outb(port, 0xD);
}

int main(int argc, char **argv)
{
  writeln(STDOUT_FD, "Hello, world!", 13);

  return 0;
}

