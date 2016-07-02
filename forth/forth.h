#ifndef __DUCKY_FORTH_H__
#define __DUCKY_FORTH_H__

/*
 * Keep values in this file in sync with its model, ducky-forth-defs.s
 */

#include <arch/ducky.h>

#define FORTH_VERSION 0x0002


#define CELL              4
#define HALFCELL          (CELL / 2)


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


#endif
