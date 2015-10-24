struct foo {
  int i;
  int j;
  char c;
  int k;
  int l;
};

struct bar {
  struct foo f1;
  struct foo *f2;
};

void fn()
{
  struct foo f, *g;
  struct bar b;
  int j;

  j = f.i;
  j = g->i;
  j = g->j;
}
