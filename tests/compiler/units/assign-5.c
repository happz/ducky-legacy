struct foo {
  int i;
  int j;
  char c;
  int k;
  int l;
};

void fn()
{
  struct foo f, *g;

  g = &f;
}
