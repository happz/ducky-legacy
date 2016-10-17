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

/*
 * Use this to declare C-defined functions as assembly-friendly.
 */
#if 0
#define ASM_CALLABLE(_fn)         _fn __attribute__((preserve_all))
#define ASM_CC                    preserve_all
#else
#define ASM_CALLABLE(_fn)         _fn __attribute__((noinline))
#define ASM_CC                    noinline
#endif


/**
 * Internal kernel structures
 */

#ifndef __DUCKY_PURE_ASM__

typedef u32_t cell_t;

typedef struct {
  u8_t  cs_len;
  char  cs_str; // first character of string
} __attribute__((packed)) counted_string_t;

/* FORTH word header */
typedef struct word_header word_header_t;

typedef cell_t cf_t;

struct word_header {
  word_header_t *      wh_link;
  u16_t                wh_name_crc;
  u8_t                 wh_flags;

  counted_string_t     wh_name;
} __attribute__((packed));

extern ASM_CALLABLE(int fw_search(char *, u32_t, word_header_t **));
extern ASM_CALLABLE(cf_t *fw_cfa(word_header_t *word));

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
};

#endif // __DUCKY_PURE_ASM__


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
extern ASM_CALLABLE(void bzero(char *, u32_t));
extern void __c_memcpy(char *dst, char *src, u32_t len);
extern u16_t __c_strcrc(char *s, u8_t len);

// TTY output
extern ASM_CALLABLE(void putc(char ));
extern ASM_CALLABLE(void puts(char *, u32_t));
extern ASM_CALLABLE(void putcs(char *));
extern ASM_CALLABLE(void putnl(void));

#define BR() do { putc('\r'); putc('\n'); } while(0)

// "Print <something>" helpers
extern ASM_CALLABLE(void do_print_prompt(void));
extern ASM_CALLABLE(void print_prompt(u32_t));

extern ASM_CALLABLE(void print_buffer(char *, u32_t));
extern ASM_CALLABLE(void print_word_name(word_header_t *));
extern ASM_CALLABLE(void print_input_buffer(void));
extern ASM_CALLABLE(void print_word_buffer(void));
extern ASM_CALLABLE(void print_input(void));

extern ASM_CALLABLE(void print_hex(u32_t u));

// Errors and exceptions
extern void halt(int errno) __attribute__((noreturn));
extern void __ERR_die(char *msg, int errno) __attribute__((noreturn));
extern void __ERR_die_with_input(char *msg, int exit_code) __attribute__((noreturn));
#ifdef FORTH_DIE_ON_UNDEF
extern void __ERR_undefined_word(void) __attribute__((noreturn));
#else
extern void __ERR_undefined_word(void);
#endif
extern void __ERR_no_interpretation_semantics(void) __attribute__((noreturn));
extern void __ERR_malformed_HDT(void) __attribute__((noreturn));
extern void __ERR_input_stack_overflow(void) __attribute__((noreturn));
extern void __ERR_input_stack_underflow(void) __attribute__((noreturn));
extern void __ERR_unknown(void) __attribute__((noreturn));
extern void __ERR_interpret_fail(void) __attribute__((noreturn));

// Input processing
extern input_desc_t *current_input;

extern ASM_CALLABLE(void input_stack_pop(void));
extern ASM_CALLABLE(void input_stack_push(input_desc_t *));

extern ASM_CALLABLE(void __refill_input_buffer(void));
extern ASM_CALLABLE(u32_t __read_line_from_kbd(char *, u32_t));

extern ASM_CALLABLE(u8_t __read_char(void));
extern ASM_CALLABLE(u8_t *__read_word(char));
extern ASM_CALLABLE(u8_t *__read_word_with_refill(char delimiter));
extern ASM_CALLABLE(u8_t *__read_dword(void));
extern ASM_CALLABLE(u8_t *__read_dword_with_refill(void));

extern ASM_CALLABLE(void flush_input_buffer(void));

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

// Number parsing
typedef struct __attribute__((packed)) {
  i32_t nr_number;
  i32_t nr_remaining;
} parse_number_result_t;

extern ASM_CALLABLE(void parse_number(char *, u32_t, parse_number_result_t * __attribute__((align_value(4)))));
extern ASM_CALLABLE(void print_unsigned(u32_t));
extern ASM_CALLABLE(void print_signed(u32_t));

// Interpreter loop
typedef enum {
  NOP          = 0,
  EXECUTE_WORD = 1,
  EXECUTE_LIT  = 2,
  COMPILE_LIT  = 3
} interpret_status_t;

typedef struct __attribute__((packed)) {
  interpret_status_t id_status;

  union {
    cf_t *             id_cfa;
    u32_t              id_number;
  } u;
} interpret_decision_t;

typedef struct {
  char * pr_word;
  u32_t  pr_length;
} parse_result_t;


/*
 * These functions implement different FORTH words. As such, they are callable
 * by their assembly wrappers.
 */

extern void do_BYE(void) __attribute__((ASM_CC,noreturn));
extern ASM_CALLABLE(void do_PAREN(void));
extern ASM_CALLABLE(void do_COMMA(u32_t));
extern ASM_CALLABLE(void do_CR(void));
extern ASM_CALLABLE(void do_DOT_PAREN(void));
extern ASM_CALLABLE(environment_query_status_t do_ENVIRONMENT_QUERY(char *, u32_t, environment_query_result_t *));
extern ASM_CALLABLE(void do_EVALUATE(char *, u32_t));
extern ASM_CALLABLE(void do_INTERPRET(interpret_decision_t *));
extern ASM_CALLABLE(void do_LITSTRING(cf_t *));
extern ASM_CALLABLE(void do_PARSE(char, parse_result_t *));
extern ASM_CALLABLE(void do_SPACE(void));
extern ASM_CALLABLE(void do_SPACES(i32_t n));
extern ASM_CALLABLE(cf_t *do_TCFA(word_header_t *));
extern ASM_CALLABLE(u32_t *do_TOIN(void));
extern ASM_CALLABLE(u32_t do_UWIDTH(u32_t));

#endif // __DUCKY_PURE_ASM__

/*
 * Following macros and definitions are used in the assembly
 * sources.
 */

#ifdef __DUCKY_PURE_ASM__

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

#define DEFCSTUB(name, len, flags, label)        \
  DEFCODE(name, len, flags, label)               \
                                                 \
  call do_ ## label                              \
  NEXT


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

#define UNPACK_WORD_FOR_FIND() \
   mov r1, r0    /* copy c-addr to r1 */  \
   inc r0        /* point r0 to string */ \
   lb r1, r1     /* load string length */

#endif // __DUCKY_PURE_ASM__

#endif
