#include <forth.h>

ASM_STRUCT(counted_string_t, word_buffer_length);

#define cs_print(_s) do { puts(&(_s)->cs_str, (_s)->cs_len); } while(0)

static void print_buffer(char *buff, u32_t len)
{
  putcs(">>>"); puts(buff, len); putcs("<<<");
}

static void print_input_buffer(void)
{
  print_buffer(current_input->id_buffer, current_input->id_length); BR();
}

static void print_word_buffer(counted_string_t *wb)
{
  print_buffer(&wb->cs_str, wb->cs_len); BR();
}

static void print_input(void)
{
  putcs("Input buffer: "); print_input_buffer();
  putcs("Word buffer: "); print_word_buffer(&word_buffer_length);
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
void __ERR_undefined_word()
{
  putcs("\r\nERROR: " XSTR(ERR_UNDEFINED_WORD) ": Undefined word\r\n");
  print_input();
#ifdef CONFIG_DIE_ON_UNDEF
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
 * Raised when BIO operation failed for some reason.
 */
void __ERR_bio_fail(u32_t storage, u32_t bid, u32_t status, int errno)
{
  printf("\r\nERROR: %d: BIO fail: storage=0x%08X, bid=0x%08X, status=0x%08X, errno=%d\r\n", ERR_BIO_FAIL, storage, bid, status, errno);
  halt(ERR_BIO_FAIL);
}

/*
 * Raised on word buffer overflow.
 */
void __ERR_word_too_long()
{
  __ERR_die_with_input("\r\nERROR: " XSTR(ERR_WORD_TOO_LONG) ": word too long:\r\n", ERR_WORD_TOO_LONG);
}

/*
 * Raised when unhandled error appears.
 */
void __ERR_unknown(void)
{
  __ERR_die_with_input("\r\nERROR: " XSTR(ERR_UNKNOWN) ": Unknown error happened\r\n", ERR_UNKNOWN);
}
