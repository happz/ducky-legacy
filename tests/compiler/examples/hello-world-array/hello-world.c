static void outb(int port, char c)
{
  asm("outb r1, r2");
}

static void writes(char s[])
{
  int i;

  for(i = 0; s[i] != '\0'; i++)
    outb(512, s[i]);
}

int main(int argc, char **argv)
{
  writes("Hello, world!\n");

  return 0;
}
