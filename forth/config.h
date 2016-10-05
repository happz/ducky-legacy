#ifndef __DUCKY_FORTH_CONFIG_H__
#define __DUCKY_FORTH_CONFIG_H__

/*
 * Cell width, in bytes. This is not actually configurable, changing this value
 * might lead to very strange things...
 */
#define CELL_WIDTH                     4
#define CELL                           CELL_WIDTH

#define HALFCELL_WIDTH                 2
#define HALFCELL                       HALFCELL_WIDTH


#define INPUT_BUFFER_SIZE 512
#define INPUT_STACK_DEPTH 8
#define PNO_BUFFER_SIZE   64

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
# define WORD_BUFFER_SIZE              STRING_SIZE
#endif

/*
 * Frequency of RTC ticks.
 *
 * By default, 1 tick per second is good enough for us.
 */
#ifndef RTC_FREQ
# define RTC_FREQ        0x0001
#endif

/*
 * This value marks the beginning of memory available for user's
 * content - words, variables, and other data.
 *
 * This must match the corresponding values in linker script.
 */
#ifndef USERSPACE_BASE
# define USERSPACE_BASE                0x9000
#endif

/*
 * Length of pre-allocated space in userspace area.
 *
 * This setting has actually not much influence on any functionality.
 * It serves basically for printing.
 */
#ifndef USERSPACE_SIZE
# define USERSPACE_SIZE                8192
#endif


/*
 * Registers
 *
 * Few registers are considered to be "reserved". This is not forced by any
 * calling convention - I simply raly on the fact there's quire a lot of
 * registers, and compiler will never need to overwrite these. That is,
 * of course, foolish, and it will bite me one day.
 */

#define FIP                            r29  // FORTH "instruction pointer"
#define PSP                            sp   // Data stack pointer
#define RSP                            r28  // Return stack pointer
#define W                              r27  // Scratch register
#define X                              r26  // Scratch register
#define Y                              r25  // Scratch register
#define Z                              r24  // Scratch register
#define TOS                            r23  // Top Of the Stack

#endif
