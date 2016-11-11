#include "forth.h"

void do_BYE()
{
  static char __bye_message[] = "\r\nBye.\r\n";

  putcs(__bye_message);
  halt(0);
}

static char __ducky_welcome[] = "\r\n"
                                "\r\n"
                                "                     ____             _          _____ ___  ____ _____ _   _ \r\n"
                                "          \033[93m__\033[0m        |  _ \\ _   _  ___| | ___   _|  ___/ _ \\|  _ \\_   _| | | |\r\n"
                                "        \033[31m<\033[0m\033[93m(o )___\033[0m    | | | | | | |/ __| |/ / | | | |_ | | | | |_) || | | |_| |\r\n"
                                "         \033[93m( ._> /\033[0m    | |_| | |_| | (__|   <| |_| |  _|| |_| |  _ < | | |  _  |\r\n"
                                "          \033[93m`---'\033[0m     |____/ \\__,_|\\___|_|\\_\\\\__, |_|   \\___/|_| \\_\\|_| |_| |_|\r\n"
                                "                                           |___/                                 \r\n\n\n";

void do_WELCOME()
{
  ASM_INT(u32_t, var_TEST_MODE);
  ASM_INT(u32_t, var_SHOW_PROMPT);
  ASM_INT(u32_t, var_ECHO);

  if (var_TEST_MODE == FORTH_TRUE)
    return;

  putcs(__ducky_welcome);

  printf("DuckyFORTH ver. %d.%d\r\n", FORTH_VERSION >> 8, FORTH_VERSION & 0xFF);
  printf("Build " XSTR(__BUILD_STAMP__) "\r\n");
  printf("%d cells remaining\r\n", CONFIG_RAM_SIZE - (u32_t)var_DP);
  printf("Type \"BYE\" to exit.\r\n");
  BR();

  var_SHOW_PROMPT = FORTH_TRUE;
  var_ECHO = FORTH_TRUE;
}
