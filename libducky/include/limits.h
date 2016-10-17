#ifndef __DUCKY_LIMITS_H__
#define __DUCKY_LIMITS_H__

#define CHAR_BIT 8

/* Minimum and maximum values a `signed char` can hold. */
#define SCHAR_MIN   (-128)
#define SCHAR_MAX   127

/* Minimum and maximum values an `unsigned char` can hold. */
#define UCHAR_MIN   0
#define UCHAR_MAX   255

/* Minimum and maximum values a `char` can hold. */
#define CHAR_MIN    SCHAR_MIN
#define CHAR_MAX    SCHAR_MAX

/* Minimum and maximum values a `signed short int` can hold. */
#define SHRT_MIN    (-32768)
#define SHRT_MAX    32767

/* Minimum and maximum values an `unsigned short` can hold. */
#define USHRT_MIN    0
#define USHRT_MAX    65535

/* Minimum and maximum values a `signed int` can hold. */
#define INT_MIN      (-2147483648)
#define INT_MAX      2147483647

/* Minimum and maximum values an `unsigned int` can hold. */
#define UINT_MIN     0
#define UINT_MAX     4294967295U

#endif // __DUCKY_LIMITS_H__
