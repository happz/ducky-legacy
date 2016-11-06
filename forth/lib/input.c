/**
 * Functions related to input buffer and its refilling.
 */

#include <forth.h>
#include <arch/keyboard.h>


//-----------------------------------------------------------------------------
// Input stack
//-----------------------------------------------------------------------------

// Bottom of the input stack is a keyboard "input".
static input_refiller_status_t __refill_input_buffer_kbd(input_desc_t *);
static char  __kbd_input_buffer[INPUT_BUFFER_SIZE];

static input_desc_t kbd_input = {
  .id_source_id    = 0,
  .id_refiller     = __refill_input_buffer_kbd,
  .id_buffer       = __kbd_input_buffer,
  .id_max_length   = INPUT_BUFFER_SIZE,
  .id_blk          = 0
};

// Input stack, with its unremovable, default "bottom".
static input_desc_t *input_stack[INPUT_STACK_DEPTH] = {
  &kbd_input
};
static int input_stack_index = 0;

input_desc_t *current_input = &kbd_input;

/*
 * Remove current input descriptor, and replace it with the previous one.
 */
void input_stack_pop()
{
  if (input_stack_index == 0)
    __ERR_input_stack_underflow();

  current_input = input_stack[--input_stack_index];
}

/*
 * Set current input to a new input descriptor.
 */
void input_stack_push(input_desc_t *input)
{
  if (input_stack_index == INPUT_STACK_DEPTH)
    __ERR_input_stack_overflow();

  current_input = input_stack[++input_stack_index] = input;
}


//-----------------------------------------------------------------------------
// Refilling input buffer
//-----------------------------------------------------------------------------

static u8_t *kbd_mmio_address = (u8_t *)(CONFIG_KBD_MMIO_BASE + KBD_MMIO_DATA);

/*
 * Read 1 character from keyboard's data port.
 *
 * If there are no characters available in keyboard buffer, the function
 * will block until interrupt arrives (possible race condition...).
 */
static u8_t __read_raw_kbd_char(void)
{
  u8_t c;

  while (1) {
    // Fetch a single character from keyboard
    c = *kbd_mmio_address;

    // No data available? Idle until there are some chars to read.
    if (c == 0xFF) {
      __idle();
      continue;
    }

    return c;
  }
}

/*
 * Handling of control characters.
 */
#define _LEFT1() do { putc(27); putc('\b'); } while(0)

/*
 * Consume control characters. Returns next incomming character.
 */
static u8_t __consume_control_chars(u8_t c, u32_t *index)
{
  if (c == 0x08) {
    // Backspace

    if (*index == 0)
      return 0xFF;

    _LEFT1(); putc(' '); _LEFT1();
    (*index)--;

    return __read_raw_kbd_char();
  }

  return c;
}

/*
 * The "refill input buffer" function. It's only job is to get new data
 * from current input, and revert to a previous one if that's no longer
 * possible.
 */
void __refill_input_buffer()
{
  do {
    switch(current_input->id_refiller(current_input)) {
      case OK:
        return;
      case EMPTY:
        input_stack_pop();
        return;
      case NO_INPUT:
        break;
    }
  } while(1);
}

ASM_INT(u32_t, var_ECHO);

/*
 * Read one line from keyboard buffer.
 */
u32_t __read_line_from_kbd(char *buff, u32_t max_length)
{
  // Zero maximal length is an ambiguous condition
  if (!max_length)
    __ERR_unknown();

  u32_t i = 0, max = max_length;
  int echo_enabled = (var_ECHO == FORTH_TRUE ? 1 : 0);
  u8_t c;

  while(max > 0) {
    c = __read_raw_kbd_char();

    c = __consume_control_chars(c, &i);
    if (c == 0xFF)
      continue;

    // Print char if echo is enabled
    if (echo_enabled)
      putc(c);

    if (c == '\r' || c == '\n')
      break;

    buff[i++] = c;
    max--;
  }

  return i;
}

/*
 * Refill input buffer for a keyboard input. This transforms to "read
 * one line from keyboard". Other input types can read more than one
 * line, keyboard input iterates over lines.
 */
static input_refiller_status_t __refill_input_buffer_kbd(input_desc_t *input)
{
  input->id_length = __read_line_from_kbd(input->id_buffer, input->id_max_length);
  input->id_index = 0;

  return OK;
}


//-----------------------------------------------------------------------------
// Input buffer processing
//-----------------------------------------------------------------------------

// These are defined in assembly - word buffer and its index can
// make use of extra ordering without any alignment between them,
// it's possible to consider them as a single counted string then.
ASM_STRUCT(counted_string_t, word_buffer_length);
ASM_INT(u32_t, var_SHOW_PROMPT);

/*
 * Read 1 character from input buffer. Return character, or 0x00 when no input
 * is available.
 */
u8_t __read_char()
{
  u8_t c;

  DEBUG_printf("__read_char: buffer=0x%08X, index=%u, current position=0x%08X\r\n", (u32_t)current_input->id_buffer, current_input->id_index, (u32_t)(current_input->id_buffer + current_input->id_index));

  if (current_input->id_index == current_input->id_length) {
    c = '\0';
  } else {
    c = *(current_input->id_buffer + current_input->id_index++);
  }

  return c;
}


/*
 *
 * Read characters from input buffer. Skip leading delimiters, then copy the following
 * characters into word buffer, until raching the end of input buffer or the delimiter
 * is encountered. Return pointer to the read word - which is actually *always*
 * pointer to word_buffer_length.
 *
 * If the input buffer is empty when __read_word is called, word buffer length is set
 * to zero.
 */
counted_string_t *__read_word(char delimiter)
{
  DEBUG_printf("__read_word: delimiter=%x, id_blk=%u\r\n", delimiter, current_input->id_blk);

  u8_t c;

  counted_string_t *wb = &word_buffer_length;
  wb->cs_len = 0;

  do {
    c = __read_char();

    DEBUG_printf("__read_word: c=%x\r\n", c);

    if (c == '\0')
      return wb;

    if (c == delimiter)
      continue;

    if (c < ' ')
      continue;

    break;
  } while(1);

  DEBUG_printf("__read_word: parsing word\r\n");

  char *buff = &wb->cs_str;

  do {
    // using "*buff++ = c" makes llvm to add some offset of -1 to the store :/
    buff[wb->cs_len++] = c;

    c = __read_char();

    if (c == '\0')
      break;

    if (c == delimiter)
      break;

    if (c < ' ')
      break;

    if (wb->cs_len == WORD_BUFFER_SIZE)
      __ERR_word_too_long();

  } while(1);

  DEBUG_printf("__read_word: got word: '%C', len=%d\r\n", &wb->cs_str, wb->cs_len, wb->cs_len);

  return wb;
}

/*
 * Does the same as __read_word, however when there's no word available in
 * input buffer (e.g. only white space remains un-parsed), it asks for refill.
 */
counted_string_t *__read_word_with_refill(char delimiter)
{
  counted_string_t *word;

  do {
    word = __read_word(delimiter);

    if (word->cs_len != 0)
      break;

    print_prompt(var_SHOW_PROMPT);

    __refill_input_buffer();
  } while(1);

  return word;
}

/*
 * __read_word with space as a delimiter.
 */
counted_string_t *__read_dword()
{
  return __read_word(' ');
}

/*
 * __read_word_with_refill with space as a delimiter.
 */
counted_string_t *__read_dword_with_refill()
{
  return __read_word_with_refill(' ');
}
