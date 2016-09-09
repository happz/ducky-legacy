#include <forth.h>

void do_BYE()
{
  static char __bye_message[] = "\r\nBye.\r\n";

  putcs(__bye_message);
  halt(0);
}
