#include <forth.h>

ASM_INT(u32_t,   var_STATE);
ASM_INT(u32_t,   var_SHOW_PROMPT);


/*
 * EVALUATE implementation
 */
static input_desc_t evaluate_stack[INPUT_STACK_DEPTH];
static int evaluate_stack_index = 0;

static input_refiller_status_t __evaluate_refiller(input_desc_t *input)
{
  evaluate_stack_index--;
  return EMPTY;
}

void do_EVALUATE(char *buff, u32_t length)
{
  if (evaluate_stack_index == INPUT_STACK_DEPTH)
    __ERR_input_stack_overflow();

  input_desc_t *input = &evaluate_stack[evaluate_stack_index++];

  input->id_source_id = -1;
  input->id_refiller = __evaluate_refiller;
  input->id_buffer = buff;
  input->id_length = length;
  input->id_index = 0;
  input->id_max_length = length;

  input_stack_push(input);
}


/*
 * This word is the most inner core of the outer interpreter. It will read
 * words from input buffer - refilling it when necessary - and execute them.
 */
ASM_BYTE(char, word_buffer);
ASM_BYTE(u8_t, word_buffer_length);
ASM_INT(cell_t, LIT);

void do_INTERPRET(interpret_decision_t *decision)
{
#define SIGNAL_NOP()       do { decision->id_status = NOP;          /*putc('N'); BR();*/ return; } while(0)
#define SIGNAL_EXEC_WORD() do { decision->id_status = EXECUTE_WORD; /*putc('W'); putc(' '); print_hex((u32_t)decision->u.id_cfa); BR();*/ return; } while(0)
#define SIGNAL_EXEC_LIT()  do { decision->id_status = EXECUTE_LIT;  /*putc('L'); putc(' '); print_hex(decision->u.id_number); BR(); */return; } while(0)

  u8_t *word_len;

  word_len = __read_word(' ');

  if (!*word_len) {
    print_prompt(var_SHOW_PROMPT);
    __refill_input_buffer();

    SIGNAL_NOP();
  }

#ifdef FORTH_DEBUG
  //print_buffer(&word_buffer, word_buffer_length);
  //putc(' ');
#endif

  word_header_t *word;
  int found;

  found = fw_search(&word_buffer, word_buffer_length, &word);

  if (found) {
    decision->u.id_cfa = do_TCFA(word);

    if (word->wh_flags & F_IMMED || var_STATE == 0)
      SIGNAL_EXEC_WORD();

    do_COMMA((u32_t)decision->u.id_cfa);
    SIGNAL_NOP();
  }

  parse_number_result_t pnr;
  parse_number(&word_buffer, word_buffer_length, &pnr);

  if (pnr.nr_remaining != 0) {
    __ERR_undefined_word();

    var_STATE = 0;
    __refill_input_buffer();
    SIGNAL_NOP();
  }

  if (var_STATE == 0) {
    decision->u.id_number = pnr.nr_number;
    SIGNAL_EXEC_LIT();
  }

  do_COMMA((u32_t)&LIT);
  do_COMMA(pnr.nr_number);

  SIGNAL_NOP();
}

/*
 * PARSE implementation
 */
void do_PARSE(char delimiter, parse_result_t *result)
{
  u8_t c;

  do {
    c = __read_char();

    if (c == '\0') {
      result->pr_length = 0;
      return;
    }

    if (c == delimiter)
      continue;

    if (c == ' ')
      continue;

    break;
  } while(1);

  result->pr_word = &current_input->id_buffer[current_input->id_index];
  result->pr_length = 0;

  do {
    result->pr_length++;

    c = __read_char();

    if (c == '\0')
      break;

    if (c == delimiter)
      break;

  } while(1);
}


/*
 * Compilation: Perform the execution semantics given below.
 * Execution: ( "ccc<paren>" -- )
 *
 * Parse `ccc` delimited by `)`. `(` is an immediate word.
 *
 * The number of characters in `ccc` may be zero to the number of characters
 * in the parse area.
 */
void do_PAREN()
{
  char c;

  do {
    c = __read_char();

    if (c == '\0') {
      __refill_input_buffer();
      continue;
    }
  } while(c != ')');
}


/*
 * >CFA implementation.
 */
cf_t *do_TCFA(word_header_t *word)
{
  return fw_cfa(word);
}


u32_t *do_TOIN()
{
  return &current_input->id_index;
}
