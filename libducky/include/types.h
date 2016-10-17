#ifndef __DUCKY_TYPES_H__
#define __DUCKY_TYPES_H__

#ifndef __DUCKY_PURE_ASM__

typedef signed char i8_t;
typedef unsigned char u8_t;
typedef signed short i16_t;
typedef unsigned short u16_t;
typedef signed int i32_t;
typedef unsigned int u32_t;

typedef u32_t uptr_t;
typedef i32_t iptr_t;


typedef i8_t int8_t;
typedef i16_t int16_t;
typedef i32_t int32_t;

typedef u8_t uint8_t;
typedef u16_t uint16_t;
typedef u32_t uint32_t;

typedef u32_t size_t;
typedef i32_t ssize_t;

typedef i32_t intptr_t;
typedef u32_t uintptr_t;

#endif // __DUCKY_PURE_ASM__

#endif // __DUCKY_TYPES_H__
