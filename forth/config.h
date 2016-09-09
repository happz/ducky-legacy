#ifndef __DUCKY_FORTH_CONFIG_H__
#define __DUCKY_FORTH_CONFIG_H__

/*
 * Cell width, in bytes. This is not actually configurable, changing this value
 * might lead to very strange things...
 */
#define CELL_WIDTH                     (4)

#define INPUT_BUFFER_SIZE 512
#define INPUT_STACK_DEPTH 8

/*
 * Counted string length, in characters.
 */
#ifndef STRING_SIZE
# define STRING_SIZE                   255
#endif

/*
 * Data stack size, in bytes.
 */
#ifndef DSTACK_SIZE
# define DSTACK_SIZE 256
#endif

/*
 * Data stack size, in cells.
 */
#define DSTACK_CELLS                   (DSTACK_SIZE / CELL_WIDTH)

/*
 * Return stack size, in bytes.
 */
#ifndef RSTACK_SIZE
# define RSTACK_SIZE 256
#endif

/*
 * Return stack size, in cells.
 */
#define RSTACK_CELLS                   (RSTACK_SIZE / CELL_WIDTH)

/*
 * Word buffer length, in bytes.
 *
 * According to standard, "an ambiguous condition exists if the length of the
 * parsed string is greater than the implementation-defined length of a counted
 * string" so lets re-use the string length.
 */
#ifndef WORD_BUFFER_SIZE
# define WORD_BUFFER_SIZE              (STRING_SIZE)
#endif


#ifndef RTC_FREQ
#  define RTC_FREQ        0x0001
#endif

#endif
