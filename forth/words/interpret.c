#include <forth.h>

ASM_INT(u32_t,   var_STATE);
ASM_INT(u32_t,   var_SHOW_PROMPT);


void do_BACKSLASH()
{
  if (INPUT_IS_BLK()) {
    // Move index to the beginning of the next line.
    current_input->id_index = ((current_input->id_index / CONFIG_LIST_CPL) + 1) * CONFIG_LIST_CPL;
  } else {
    // Discard the rest of input buffer by simply signaling we're at its end.
    current_input->id_index = current_input->id_length;
  }
}


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
  input->id_blk = 0;

  input_stack_push(input);
}


/*
 * This word is the most inner core of the outer interpreter. It will read
 * words from input buffer - refilling it when necessary - and execute them.
 */
ASM_INT(cell_t, LIT);
ASM_INT(cell_t, TWOLIT);

void do_INTERPRET(interpret_decision_t *decision)
{
#define SIGNAL_NOP()       do { decision->id_status = INTERPRET_NOP;          return; } while(0)
#define SIGNAL_EMPTY()     do { decision->id_status = INTERPRET_EMPTY;        return; } while(0)
#define SIGNAL_EXEC_WORD() do { decision->id_status = INTERPRET_EXECUTE_WORD; return; } while(0)
#define SIGNAL_EXEC_LIT()  do { decision->id_status = INTERPRET_EXECUTE_LIT;  return; } while(0)
#define SIGNAL_EXEC_2LIT() do { decision->id_status = INTERPRET_EXECUTE_2LIT; return; } while(0)

  counted_string_t *wb = __read_word(' ');

  if (!wb->cs_len) {
    print_prompt(var_SHOW_PROMPT);
    __refill_input_buffer();

    SIGNAL_EMPTY();
  }

  word_header_t *word;
  int found = fw_search(wb, &word);

  if (found) {
    decision->u.id_cfa = do_TCFA(word);

    if (word->wh_flags & F_IMMED || var_STATE == 0)
      SIGNAL_EXEC_WORD();

    do_COMMA((u32_t)decision->u.id_cfa);
    SIGNAL_NOP();
  }

  parse_number_result_t pnr;
  int ret = parse_number(wb, &pnr);

  if (ret == -1 || pnr.nr_remaining != 0) {
    __ERR_undefined_word();

    var_STATE = 0;
    __refill_input_buffer();
    SIGNAL_NOP();
  }

  if (ret == 0) {
    if (var_STATE == 0) {
      decision->u.id_number = pnr.nr_number_lo;
      SIGNAL_EXEC_LIT();
    }

    do_COMMA((u32_t)&LIT);
    do_COMMA(pnr.nr_number_lo);
  } else {
    if (var_STATE == 0) {
      decision->u.id_double_number[0] = pnr.nr_number_lo;
      decision->u.id_double_number[1] = pnr.nr_number_hi;
      SIGNAL_EXEC_2LIT();
    }

    do_COMMA((u32_t)&TWOLIT);
    do_COMMA(pnr.nr_number_lo);
    do_COMMA(pnr.nr_number_hi);
  }

  SIGNAL_NOP();
}

/*
 * PARSE implementation
 */
void do_PARSE(char delimiter, parse_result_t *result)
{
  u8_t c;

  result->pr_length = 0;

  c = __read_char();

  if (c == '\0')
    return;

  if (c == delimiter)
    return;

  result->pr_word = &current_input->id_buffer[current_input->id_index - 1];

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
 * ( -- flag )
 *
 * Attempt to fill the input buffer from the input source, returning a true
 * flag if successful.
 *
 * When the input source is the user input device, attempt to receive input
 * into the terminal input buffer. If successful, make the result the input
 * buffer, set >IN to zero, and return true. Receipt of a line containing no
 * characters is considered successful. If there is no input available from
 * the current input source, return false.
 *
 * When the input source is a string from EVALUATE, return false and perform
 * no other action.
 */
u32_t do_REFILL()
{
  // if the current input source is EVALUATE'ed string, simply return false.
  if (INPUT_IS_EVAL())
    return FORTH_FALSE;

  if (INPUT_IS_KBD()) {
    /* User input device (keyboard) always has data avilable - it simply waits
     * for some to arrive... Which is not correct, I guess, REFILL is supposed
     * to *test* for available data instead of waiting for them.
     */
    __refill_input_buffer();
    return FORTH_TRUE;
  }

  if (INPUT_IS_BLK()) {
    u32_t blk = current_input->id_blk + 1;
    input_stack_pop();
    do_BLK_LOAD(blk);

    return FORTH_TRUE;
  }

  return FORTH_FALSE;
}


/*
 * ( xn ... x1 n -- flag )
 *
 * Attempt to restore the input source specification to the state described by
 * x1 through xn. flag is true if the input source specification cannot be so
 * restored.
 *
 * An ambiguous condition exists if the input source represented by the arguments
 * is not the same as the current input source.
 */
void do_RESTORE_INPUT(u32_t n, u32_t *buff)
{
  DEBUG_printf("do_RESTORE_INPUT: n=%u, buff=0x%08X, #0=%u, #1=%u\r\n", n, (u32_t)buff, buff[0], buff[1]);

  if (n == 2) {
    /*
     * Input was saved with block as an input device, therefore
     * it is expected to being restored in the context of the
     * same device - however the actual block may be different.
     * Drop the current block (by dropping the current input),
     * and load the block we saved before. This way we can be
     * sure we're parsing the correct block no matter what.
     */
    input_stack_pop();
    do_BLK_LOAD(buff[1]);
  }

  current_input->id_index = buff[0];
}

/*
 * ( -- xn ... x1 n )
 *
 * x1 through xn describe the current state of the input source specification
 * for later use by RESTORE-INPUT.
 */
u32_t do_SAVE_INPUT(u32_t *buff)
{
  /* SAVE-INPUT & RESTORE-INPUT *must* be used with the very same input source
   * set as the current input.
   */

  DEBUG_printf("do_SAVE_INPUT: buff=0x%08X\r\n", (u32_t)buff);

  buff[0] = current_input->id_index;
  buff[1] = current_input->id_blk;

  DEBUG_printf("do_SAVE_INPUT: #0=%u, #1=%u, ret=%u\r\n", buff[0], buff[1], (INPUT_IS_BLK() ? 2 : 1));
  return (INPUT_IS_BLK() ? 2 : 1);
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
