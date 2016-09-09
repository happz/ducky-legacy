#include <forth.h>

static char *__input_buffer_label = "Input buffer: ";
static char *__word_buffer_label  = "Word buffer: ";

static char __buffer_prefix[]      = ">>>";
static char __buffer_postfix[]     = "<<<";

ASM_BYTE(char, word_buffer);
ASM_BYTE(u8_t, word_buffer_length);

void print_buffer(char *buff, u32_t len)
{
  putcs(__buffer_prefix);
  puts(buff, len);
  putcs(__buffer_postfix);
}

void print_word_name(word_header_t *header)
{
  puts(&header->wh_name.cs_str, header->wh_name.cs_len);
  BR();
}

void print_input_buffer(void)
{
  print_buffer(current_input->id_buffer, current_input->id_length);
  BR();
}

void print_word_buffer(void)
{
  print_buffer(&word_buffer, word_buffer_length);
  BR();
}

void print_input(void)
{
  putcs(__input_buffer_label);
  print_input_buffer();

  putcs(__word_buffer_label);
  print_word_buffer();
}


/*
 * Error handlers
 */
void __ERR_die(char *msg, int exit_code)
{
  putcs(msg);
  halt(exit_code);
}

void __ERR_die_with_input(char *msg, int exit_code)
{
  putcs(msg);
  print_input();

  halt(exit_code);
}

/*
 * Raised when word is not in dictionary, and it is not a number.
 */
void __ERR_undefined_word(void)
{
  putcs("\r\nERROR: " XSTR(ERR_UNDEFINED_WORD) ": Undefined word\r\n");
  print_input();
#ifdef FORTH_DIE_ON_UNDEF
  halt(ERR_UNDEFINED_WORD);
#endif
}

/*
 * Raised when word with undefined interpretation semantics is executed
 * in interpretation state.
 */
void __ERR_no_interpretation_semantics(void) 
{
  __ERR_die_with_input("\r\nERROR: " XSTR(ERR_NO_INTERPRET_SEMANTICS) ": Word has undefined interpretation semantics\r\n", ERR_NO_INTERPRET_SEMANTICS);
}

/*
 * Raised when HDT is malformed.
 */
void __ERR_malformed_HDT(void)
{
  halt(ERR_MALFORMED_HDT);
}

/*
 * Raised when something triggers unhandled exception.
 */
void __ERR_unhandled_exception(void)
{
  __ERR_die("\r\nERROR: " XSTR(ERR_UNHANDLED_IRQ) ": Unhandled irq\r\n", ERR_UNHANDLED_IRQ);
}

/*
 * Raised when input stack is full.
 */
void __ERR_input_stack_overflow(void)
{
  __ERR_die("\r\nERROR: " XSTR(ERR_INPUT_STACK_OVERFLOW) ": Input stack overflow\r\n", ERR_INPUT_STACK_OVERFLOW);
}

/*
 * Raised when there's only last item on input stack.
 */
void __ERR_input_stack_underflow(void)
{
  __ERR_die("\r\nERROR: " XSTR(ERR_INPUT_STACK_UNDERFLOW) ": Input stack underflow\r\n", ERR_INPUT_STACK_UNDERFLOW);
}

/*
 * Raised when INTERPRET does not know what to do.
 */
void __ERR_interpret_fail()
{
  __ERR_die("\r\nERROR: " XSTR(ERR_INTERPRET_FAIL) ": Interpret fail\r\n", ERR_INTERPRET_FAIL);
}

/*
 * Raised when unhandled error appears.
 */
void __ERR_unknown(void)
{
  __ERR_die_with_input("\r\nERROR: " XSTR(ERR_UNKNOWN) ": Unknown error happened\r\n", ERR_UNKNOWN);
}
