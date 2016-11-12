#ifndef __DUCKY_FORTH_CONFIG_H__
#define __DUCKY_FORTH_CONFIG_H__


//-----------------------------------------------------------------------------
// Hardware setup
//-----------------------------------------------------------------------------

#ifndef CONFIG_RTC_MMIO_BASE
#  define CONFIG_RTC_MMIO_BASE         0x700
#endif

#ifndef CONFIG_KBD_MMIO_BASE
#  define CONFIG_KBD_MMIO_BASE         0x800
#endif

#ifndef CONFIG_TTY_MMIO_BASE
#  define CONFIG_TTY_MMIO_BASE         0x900
#endif

#ifndef CONFIG_BIO_MMIO_BASE
#  define CONFIG_BIO_MMIO_BASE         0x600
#endif

#ifndef CONFIG_RAM_SIZE
#  define CONFIG_RAM_SIZE              0x1000000
#endif


//-----------------------------------------------------------------------------
// Optional settings
//-----------------------------------------------------------------------------

/*
 * Enable test mode - no "ok" prompt, for example.
 */
#ifndef CONFIG_TEST_MODE
#  define CONFIG_TEST_MODE             0x00000000
#endif


/*
 * Enable initial terminal echo.
 */
#ifndef CONFIG_ECHO
#  define CONFIG_ECHO                  0xFFFFFFFF
#endif


/*
 * If defined, interpreter will quit with error when undefined word is
 * encountered.
 */
#ifndef CONFIG_DIE_ON_UNDEF
#  define CONFIG_DIE_ON_UNDEF          0
#endif


/*
 * Cell width, in bytes. This is not actually configurable, changing this value
 * might lead to very strange things...
 */
#define CELL_WIDTH                     4
#define CELL                           CELL_WIDTH

#define HALFCELL_WIDTH                 2
#define HALFCELL                       HALFCELL_WIDTH

#define DOUBLECELL_WIDTH               8
#define DOUBLECELL                     DOUBLECELL_WIDTH


#define INPUT_BUFFER_SIZE 512
#define INPUT_STACK_DEPTH 8

/*
 * Pictured numeric output buffer size, in bytes.
 *
 * Should be at least (2 * n) + 2 bytes, where N is number of bits in cell.
 */
#ifndef CONFIG_PNO_BUFFER_SIZE
#  define CONFIG_PNO_BUFFER_SIZE       66
#endif


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
# define USERSPACE_BASE                0x0000B000
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
 * Length of PAD region
 *
 * PAD region could be allocated dynamicaly but I rather have it
 * prepared statically.
 */
#ifndef CONFIG_PAD_SIZE
#  define CONFIG_PAD_SIZE              STRING_SIZE
#endif


/*
 * Number of blocks kernel can keep in memory simultaneously.
 */
#ifndef CONFIG_BLOCK_CACHE_SIZE
#  define CONFIG_BLOCK_CACHE_SIZE      8
#endif

/*
 * ID of the mass storage available for FORTH code.
 */
#ifndef CONFIG_BLOCK_STORAGE
#  define CONFIG_BLOCK_STORAGE         1
#endif


//-----------------------------------------------------------------------------
// Optimization settings
//-----------------------------------------------------------------------------

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

/*
 * Peep hole optimization.
 * If enabled, compiler will try to optimize words by replacing sequence
 * of words with more effective equivalents (e.g. sequence of "LIT", "1"
 * will be replaced by a single word).
 */
#ifndef CONFIG_PEEPHOLE
#  define CONFIG_PEEPHOLE              1
#endif


/*
 * Size of internal printf buffer.
 */
#ifndef CONFIG_PRINTF_BUFFER_SIZE
#  define CONFIG_PRINTF_BUFFER_SIZE   PAGE_SIZE
#endif


/*
 * Number of lines per screen when LISTing blocks.
 */
#ifndef CONFIG_LIST_LPS
#  define CONFIG_LIST_LPS              16
#endif

/*
 * Number of characters per line when LISTing blocks.
 */
#ifndef CONFIG_LIST_CPL
#  define CONFIG_LIST_CPL              64
#endif

//-----------------------------------------------------------------------------
// Debugging options
//-----------------------------------------------------------------------------

#ifndef DEBUG
#  define DEBUG                        0
#endif


/*
 * Set this to 1 if you want to set malloc()'ed and free()'ed memory to
 * specific, "red-zone" values.
 */
#ifndef CONFIG_MALLOC_REDZONE
#  define CONFIG_MALLOC_REDZONE 0
#endif

#endif
