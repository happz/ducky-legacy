#ifndef __DUCKY_FORTH_H__
#define __DUCKY_FORTH_H__

/*
 * Keep values in this file in sync with its model, ducky-forth-defs.s
 */

#include <config.h>
#include <arch/ducky.h>

#define FORTH_VERSION 0x0002


#define CELL              4
#define HALFCELL          (CELL / 2)


/* Header of a FORTH word */
typedef struct forth_word_header forth_word_header_t;

// Field "wh_name" is actually the first character of name, not
// the full name. The whole struct is somewhat unaligned because
// of this.
struct forth_word_header {
  forth_word_header_t *wh_link;
  u16_t                wh_name_crc;
  u8_t                 wh_flags;
  u8_t                 wh_name_len;
  char                 wh_name;
} __attribute__((packed));

/* Word flags */
#define F_IMMED  0x0001
#define F_HIDDEN 0x0002

/* FORTH boolean "flags" */
#define FORTH_TRUE 0xFFFFFFFF
#define FORTH_FALSE 0x00000000


/* Error codes */
enum {
  ERR_UNKNOWN =                -1,
  ERR_UNDEFINED_WORD =         -2,
  ERR_UNHANDLED_IRQ =          -3,
  ERR_NO_INTERPRET_SEMANTICS = -4,
  ERR_MALFORMED_HDT =          -5,
  ERR_UNHANDLED_ARGUMENT =     -6,
};


/* Syntax sugar, to make sources more readable */

// Functions with this attribute will preserve all registers. I'd rather have
// separate calling convention for FORTH, or even better, update FORTH assembly
// code to conform to th default Ducky CC but that's quite a lot of work...
#define FORTHCC __attribute__((preserve_all))


/* Some common functions */

extern void halt(int errno) __attribute__((noreturn));
extern void __ERR_die(char *msg, int errno) __attribute__((noreturn));

#endif
