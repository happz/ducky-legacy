#ifndef __DUCKY_FORTH_H__
#define __DUCKY_FORTH_H__

#include <config.h>

#include <arch/ducky.h>
#include <stddef.h>


/*
 * Kernel version. Upper byte MAJOR, lower byte MINOR.
 */
#define FORTH_VERSION 0x0100


// Stringify helpers
#define XSTR(_e) STR(_e)
#define STR(_e) #_e


/*
 * ABI helpers
 */

// I'd rather have separate calling convention for FORTH, or even better,
// update FORTH assembly code to conform to the default Ducky CC but that's
// quite a lot of work...
#define FORTHCC __attribute__((preserve_all))


/*
 * Use these to declare assembly-defined structures in C code.
 */
#define ASM_PTR(_type, _name)     extern _type __attribute__ ((aligned (4))) _name
#define ASM_INT(_type, _name)     extern _type __attribute__ ((aligned (4))) _name
#define ASM_SHORT(_type, _name)   extern _type __attribute__ ((aligned (2))) _name
#define ASM_BYTE(_type, _name)    extern _type __attribute__ ((aligned (1))) _name
#define ASM_STRUCT(_type, _name)  extern _type __attribute__ ((aligned (4))) _name


/**
 * Internal kernel structures
 */

#ifndef __DUCKY_PURE_ASM__

typedef u32_t cell_t;

typedef struct __attribute__((packed)) {
  u8_t  cs_len;
  char  cs_str; // first character of string
} counted_string_t;

/* FORTH word header */
typedef struct word_header word_header_t;

typedef cell_t cf_t;

struct __attribute__((packed)) word_header {
  word_header_t *      wh_link;
  u16_t                wh_name_crc;
  u8_t                 wh_flags;

  counted_string_t     wh_name;
};

extern int fw_search(counted_string_t *needle, word_header_t **);

extern u32_t *fw_code_field(word_header_t *word);
extern u32_t *fw_data_field(word_header_t *word);
extern u32_t *fw_value_field(word_header_t *word);

#endif // __DUCKY_PURE_ASM__

/* Offsets of word header' fields */
#define WR_LINK                        0
#define WR_NAMECRC                     4
#define WR_FLAGS                       6
#define WR_NAMELEN                     7
#define WR_NAME                        8

/* Word flags */
#define F_IMMED                     0x0001
#define F_HIDDEN                    0x0002


/* Input stack structures */
#ifndef __DUCKY_PURE_ASM__

typedef struct input_desc input_desc_t;

typedef enum {
  OK        = 0,
  NO_INPUT  = 1,
  EMPTY     = 2
} input_refiller_status_t;

typedef input_refiller_status_t (*input_refiller_t)(input_desc_t *);

struct input_desc {
  i32_t            id_source_id;
  input_refiller_t id_refiller;

  char *           id_buffer;
  u32_t            id_length;
  u32_t            id_index;
  u32_t            id_max_length;

  u32_t            id_blk;  // BLK - non-zero if descriptor handles block
};

#define INPUT_IS_KBD()  (current_input->id_source_id == 0)
#define INPUT_IS_EVAL() (current_input->id_source_id == -1)
#define INPUT_IS_BLK()  (current_input->id_blk != 0)

#endif // __DUCKY_PURE_ASM__

/* Interpret state */
#define STATE_COMPILE                  1
#define STATE_INTERPRET                0


/* FORTH boolean "flags" */
#define FORTH_TRUE                  0xFFFFFFFF
#define FORTH_FALSE                 0x00000000


/* Error codes */
#define ERR_UNKNOWN                 1
#define ERR_UNDEFINED_WORD          2
#define ERR_UNHANDLED_IRQ           3
#define ERR_NO_INTERPRET_SEMANTICS  4
#define ERR_MALFORMED_HDT           5
#define ERR_UNHANDLED_ARGUMENT      6
#define ERR_INPUT_STACK_OVERFLOW    7
#define ERR_INPUT_STACK_UNDERFLOW   8
#define ERR_UNALIGNED_MEMORY_ACCESS 9
#define ERR_INTERPRET_FAIL          10
#define ERR_BIO_FAIL                11
#define ERR_WORD_TOO_LONG           12


/**
 * Internal kernel API
 */

#ifndef __DUCKY_PURE_ASM__

static inline u32_t align4(u32_t u)
{
  return (u + 3) & 0xFFFFFFFC;
}

#define CELL_ALIGN(_u) align4(_u)


// Low-level stuff
extern void __idle(void);

// String/memory helpers
extern int __c_strcmp(char *s1, char *s2, u32_t len1, u32_t len2);
extern void bzero(char *, u32_t);
extern void __c_memcpy(char *dst, char *src, u32_t len);
extern void memset(u8_t *dst, u32_t c, u32_t len);

extern u16_t strcrc(char *s, u8_t len);

static inline u16_t cs_crc(counted_string_t *cs) { return strcrc(&cs->cs_str, cs->cs_len); }
extern int cs_cmp(counted_string_t *s1, counted_string_t *s2);

// TTY output
extern void putc(char );
extern void puts(char *, u32_t);
extern void putcs(char *);
extern void putnl(void);

#define BR() do { putc('\r'); putc('\n'); } while(0)

// "Print <something>" helpers
extern void do_print_prompt(void);
extern void print_prompt(u32_t);

#include <stdarg.h>

extern int mini_vsnprintf(char* buffer, unsigned int buffer_len, char *fmt, va_list va);
extern int mini_snprintf(char* buffer, unsigned int buffer_len, char *fmt, ...);
extern int printf(char *fmt, ...);
extern char printf_buffer[];

#define vsnprintf mini_vsnprintf
#define snprintf mini_snprintf

// Errors and exceptions
extern void halt(int errno) __attribute__((noreturn));
extern void __ERR_die(char *msg, int errno) __attribute__((noreturn));
extern void __ERR_die_with_input(char *msg, int exit_code) __attribute__((noreturn));
#if (CONFIG_DIE_ON_UNDEF == 0)
extern void __ERR_undefined_word(void);
#else
extern void __ERR_undefined_word(void) __attribute__((noreturn));
#endif
extern void __ERR_no_interpretation_semantics(void) __attribute__((noreturn));
extern void __ERR_input_stack_overflow(void) __attribute__((noreturn));
extern void __ERR_input_stack_underflow(void) __attribute__((noreturn));
extern void __ERR_unknown(void) __attribute__((noreturn));
extern void __ERR_interpret_fail(void) __attribute__((noreturn));
extern void __ERR_bio_fail(u32_t storage, u32_t bid, u32_t status, int errno) __attribute__((noreturn));
extern void __ERR_word_too_long(void) __attribute__((noreturn));

// Input processing
extern input_desc_t *current_input;

extern void input_stack_pop(void);
extern void input_stack_push(input_desc_t *);

extern void __refill_input_buffer(void);
extern u32_t __read_line_from_kbd(char *, u32_t);

extern u8_t __read_char(void);
extern counted_string_t *__read_word(char delimiter);
extern counted_string_t *__read_word_with_refill(char delimiter);
extern counted_string_t *__read_dword(void);
extern counted_string_t *__read_dword_with_refill(void);

// Heap allocations
extern void *malloc(u32_t);
extern void free(void *);

// Enviroment queries
typedef enum {
  UNKNOWN = 0,
  NUMBER = 1,
  DOUBLE_NUMBER = 2,
  TRUE = 3,
  FALSE = 4
} environment_query_status_t;

typedef struct __attribute__((packed)) {
  u32_t                      number_lo;
  u32_t                      number_hi;
} environment_query_result_t;


/* ----------------------------------------------------------------------
 * Number parsing
 */

typedef struct {
  i32_t nr_remaining;
  i32_t nr_number_lo;
  i32_t nr_number_hi;
} parse_number_result_t;

extern int parse_number(counted_string_t *s, parse_number_result_t * __attribute__((align_value(4))) result);

extern void print_u32(u32_t u);
extern void print_i32(i32_t i);

extern void pno_reset_buffer(void);

// Interpreter loop
typedef enum {
  INTERPRET_NOP          = 0,
  INTERPRET_EMPTY        = 1,
  INTERPRET_EXECUTE_WORD = 2,
  INTERPRET_EXECUTE_LIT  = 3,
  INTERPRET_EXECUTE_2LIT = 4
} interpret_status_t;

typedef struct __attribute__((packed)) {
  interpret_status_t id_status;

  union {
    cf_t *             id_cfa;
    u32_t              id_number;
    u32_t              id_double_number[2];
  } u;
} interpret_decision_t;

typedef struct __attribute__((packed)) {
  char * pr_word;
  u32_t  pr_length;
} parse_result_t;


/*
 * Compilation helper - it's not necessary to perform full call to do_COMMA.
 */
ASM_PTR(u32_t *, var_DP);

extern void __COMPILE(u32_t u);
#define COMPILE(_u)      do { __COMPILE((u32_t)(_u)); } while(0)


/*
 * Compilation/interpreting state
 */
ASM_INT(u32_t, var_STATE);
#define IS_COMPILATION() (var_STATE == STATE_COMPILE)
#define IS_INTERPRET()   (var_STATE == STATE_INTERPRET)


/*
 * These functions implement different FORTH words. As such, they are callable
 * by their assembly wrappers.
 */

extern void do_AGAIN(u32_t *dest);
extern void do_BACKSLASH(void);
extern void do_BYE(void) __attribute__((noreturn));
extern void do_PAREN(void);
extern void do_COLON(void);
extern void do_COMMA(u32_t);
extern void do_CR(void);
extern void do_DOT_PAREN(void);
extern environment_query_status_t do_ENVIRONMENT_QUERY(char *, u32_t, environment_query_result_t *);
extern void do_EVALUATE(char *, u32_t);
extern void do_HEADER_COMMA(counted_string_t *name);
extern u32_t *do_IF(void);
extern void do_INTERPRET(interpret_decision_t *);
extern int do_ISNUMBER(counted_string_t *needle, i32_t *num);
extern void do_LITERAL(u32_t u);
extern void do_LITSTRING(cf_t *);
extern void do_PARSE(char, parse_result_t *);
extern void do_SPACE(void);
extern void do_SPACES(i32_t n);
extern cf_t *do_TCFA(word_header_t *);
extern u32_t *do_TOIN(void);
extern u32_t do_UWIDTH(u32_t);
extern void do_POSTPONE(void);
extern u32_t do_REFILL(void);
extern u32_t do_SAVE_INPUT(u32_t *buffer);
extern void do_SEMICOLON(void);
extern void do_RESTORE_INPUT(u32_t n, u32_t *buffer);
extern void *do_BLK(void);
extern void *do_BLOCK(u32_t bid);
extern void *do_BUFFER(u32_t bid);
extern void do_EMPTY_BUFFERS(void);
extern void do_FLUSH(void);
extern void do_LIST(u32_t bid);
extern void do_SAVE_BUFFERS(void);
extern void do_UPDATE(void);
extern void do_BLK_LOAD(u32_t bid);
extern void do_THRU(u32_t u1, u32_t u2);

#endif // __DUCKY_PURE_ASM__



/*
 * Following macros and definitions are used in the assembly
 * sources.
 */

#ifdef __DUCKY_PURE_ASM__

#define COMPILE __COMPILE

// Syntax sugar, to help me define variables in assembly
#define WORD(_name, _init) \
  .align CELL              \
  .type _name, word, _init \
  .global _name

#define SHORT(_name, _init) \
  .align HALFCELL           \
  .type _name, short, _init \
  .global _name

#define BYTE(_name, _init) \
  .type _name, byte, _init \
  .global _name

#define ASCII(_name, _init) \
  .type _name, ascii, _init \
  .global _name

#define SPACE(_name, _init) \
  .type _name, space, _init \
  .global _name

/* Return stack manipulation */
#define PUSHRSP(_reg) \
  sub RSP, CELL       \
  stw RSP, _reg

#define POPRSP(_reg)  \
  lw _reg, RSP        \
  add RSP, CELL


/*
 * "Move to the next word" bit, at the end of every word
 *
 * FIP points to a cell with address of a Code Field,
 * and Code Field contains address of routine.
 */

#define NEXT     \
  lw W, FIP      \
  add FIP, CELL  \
  lw X, W        \
  j X


/* Word definition macros */
#define __DEFWORD(name, len, flags, label) \
  .global label                            \
                                           \
  .section .rodata                         \
                                           \
  WORD(name_ ## label, link)               \
  .set link, name_ ## label                \
                                           \
  SHORT(__crc_ ## label, 0x7979)           \
  BYTE(__flags_ ## label, flags)           \
  BYTE(__len_ ## label, len)               \
  ASCII(__name_ ## label, name)            \
  .align CELL

#define DEFWORD(name, len, flags, label) \
  __DEFWORD(name, len, flags, label)     \
                                         \
  .type label, word, DOCOL

#define DEFDOESWORD(name, len, flags, label) \
  __DEFWORD(name, len, flags, label)         \
                                             \
  .type label, word, DODOES

#define DEFCODE(name, len, flags, label) \
  __DEFWORD(name, len, flags, label)     \
                                         \
  .global code_ ## label                 \
  .type label, word, code_ ## label      \
                                         \
  .text                                  \
code_ ## label:

#define DEFVAR(name, len, flags, label, initial) \
  DEFCODE(name, len, flags, label)               \
                                                 \
  push TOS                                       \
  la TOS, var_ ## label                          \
  NEXT                                           \
                                                 \
  .data                                          \
  .align CELL                                    \
  .type var_ ## label, word, initial             \
  .global var_ ## label

#define DEFCONST(name, len, flags, label, initial) \
  DEFCODE(name, len, flags, label)                 \
                                                   \
  push TOS                                         \
  li TOS, initial                                  \
  NEXT

#define DEFCSTUB_00(name, len, flags, label)     \
  DEFCODE(name, len, flags, label)               \
                                                 \
  call do_ ## label                              \
  NEXT

#define DEFCSTUB_10(name, len, flags, label)     \
  DEFCODE(name, len, flags, label)               \
                                                 \
  mov r0, TOS                                    \
  call do_ ## label                              \
  pop TOS                                        \
  NEXT

#define DEFCSTUB_20(name, len, flags, label)     \
  DEFCODE(name, len, flags, label)               \
                                                 \
  mov r1, TOS                                    \
  pop r0                                         \
  call do_ ## label                              \
  pop TOS                                        \
  NEXT

#define DEFCSTUB_11(name, len, flags, label)     \
  DEFCODE(name, len, flags, label)               \
                                                 \
  mov r0, TOS                                    \
  call do_ ## label                              \
  mov TOS, r0                                    \
  NEXT

#define DEFCSTUB_01(name, len, flags, label)     \
  DEFCODE(name, len, flags, label)               \
                                                 \
  push TOS                                       \
  call do_ ## label                              \
  mov TOS, r0                                    \
  NEXT

#define DEFCSTUB DEFCSTUB_00

// Compare words have always the same epilog...
#define TF_FINISH(name, true_test) \
  true_test __tf_finish_ ## name   \
  j __CMP_false                    \
__tf_finish_ ## name:              \
  j __CMP_true

#define LOAD_TRUE(reg) \
  li reg, 0xFFFF       \
  liu reg, 0xFFFF

#define LOAD_FALSE(reg) \
  li reg, 0x0000        \
  liu reg, 0x0000

#define PUSH_TRUE(reg) \
  LOAD_TRUE(reg)       \
  push reg

#define ALIGN_CELL(reg) \
  add reg, 3            \
  and reg, 0x7FFC

#endif // __DUCKY_PURE_ASM__


/*
 * Debugging options
 */

#if 0
#  define DEBUG_BLOCKS 1
#  define DEBUG_printf printf
#  define DEBUG_puts puts
#  define DEBUG_putcs putcs
#else
#  define DEBUG_BLOCKS 0
#  define DEBUG_printf(...) (void)0
#  define DEBUG_puts(a, b)  (void)0
#  define DEBUG_putcs(a)    (void)0
#endif

#endif
