static void outb(int port, char c)
{
  asm("outb r1, r2");
}

static void writes(char *s)
{
  char c;

  while((c = *s++) != '\0')
    outb(512, c);
}

int main(int argc, char **argv)
{
  writes("Hello, world!\n");

  return 0;
}
