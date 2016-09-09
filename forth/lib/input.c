/**
 * Functions related to input buffer and its refilling.
 */

#include <forth.h>


//-----------------------------------------------------------------------------
// Input stack
//-----------------------------------------------------------------------------

// Bottom of the input stack is a keyboard "input".
static ASM_CALLABLE(input_refiller_status_t __refill_input_buffer_kbd(input_desc_t *));
static char  __kbd_input_buffer[INPUT_BUFFER_SIZE];

static input_desc_t kbd_input = {
  .id_source_id    = 0,
  .id_refiller     = __refill_input_buffer_kbd,
  .id_buffer       = __kbd_input_buffer,
  .id_max_length   = INPUT_BUFFER_SIZE
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
ASM_PTR(u8_t *, kbd_mmio_address);

/*
 * Read one line from keyboard buffer.
 *
 * If there are no characters available in keyboard buffer, the function
 * will block until interrupt arrives (possible race condition...).
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
    // Fetch a single character from keyboard
    c = *kbd_mmio_address;

    // No data available? Idle until there are some chars to read.
    if (c == 0xFF) {
      __idle();
      continue;
    }

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

/*
 * Signal to others that we have reached the end of input buffer.
 * Subsequent attempts to read from it should result in its refilling.
 */
void flush_input_buffer()
{
  current_input->id_index = current_input->id_length;
}


//-----------------------------------------------------------------------------
// Input buffer processing
//-----------------------------------------------------------------------------

// These are defined in assembly - word buffer and its index can
// make use of extra ordering without any alignment between them,
// it's possible to consider them as a single counted string then.
ASM_BYTE(char, word_buffer);
ASM_BYTE(u8_t, word_buffer_length);

ASM_INT(u32_t, var_SHOW_PROMPT);

/*
 * Read 1 character from input buffer. Return character, or 0x00 when no input
 * is available.
 */
u8_t __read_char()
{
  u8_t c;

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
 * is encountered. Sets word_buffer_length properly.
 *
 * If the input buffer is empty when __read_word is called, word buffer length is set
 * to zero.
 */
u8_t *__read_word(char delimiter)
{
  u8_t c;

  do {
    c = __read_char();

    if (c == '\0') {
      word_buffer_length = 0;
      return &word_buffer_length;
    }

    if (c == delimiter)
      continue;

    if (c < ' ')
      continue;

    break;
  } while(1);

  char *buff = &word_buffer;
  u8_t len = 0;

  do {
    // using "*buff++ = c" makes llvm to add some offset of -1 to the store :/
    buff[len++] = c;

    c = __read_char();

    if (c == '\0')
      break;

    if (c == delimiter)
      break;

    if (c < ' ')
      break;

    if (len == WORD_BUFFER_SIZE) {
      print_buffer(buff, len);
      __ERR_unknown();
    }

  } while(1);

  word_buffer_length = len;

  return &word_buffer_length;
}

/*
 * Does the same as __read_word, however when there's no word available in
 * input buffer (e.g. only white space remains un-parsed), it asks for refill.
 */
u8_t *__read_word_with_refill(char delimiter)
{
  do {
    __read_word(delimiter);

    if (word_buffer_length != 0)
      break;

    print_prompt(var_SHOW_PROMPT);

    __refill_input_buffer();
  } while(1);

  return &word_buffer_length;
}

/*
 * __read_word with space as a delimiter.
 */
u8_t *__read_dword()
{
  return __read_word(' ');
}

/*
 * __read_word_with_refill with space as a delimiter.
 */
u8_t *__read_dword_with_refill()
{
  return __read_word_with_refill(' ');
}
