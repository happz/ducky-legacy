#include <types.h>
#include <hdt.h>
#include <arch/rtc.h>
#include <arch/tty.h>
#include <arch/keyboard.h>

#include <forth.h>


typedef int (*hdt_entry_handler)(hdt_entry_header_t *);

/*
 * These variables are defined in ducky-forth.s, code bellow stores values
 * in these before reporting back to caller.
 */
extern u32_t memory_size;
extern u32_t var_TEST_MODE;
extern u32_t rtc_mmio_address;
extern u32_t tty_mmio_address;
extern u32_t kbd_mmio_address;


/*
 * Internal storage for dvice names parsed from HDT
 */
static char rtc_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t rtc_device_name_length = 0;

static char tty_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t tty_device_name_length = 0;

static char kbd_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t kbd_device_name_length = 0;

/*
 * Helper functions
 *
 * It would be cool to get rid of these, and use already existing functions from
 * FORTH assembly code, but that requires to fix their calling conventions to
 * match the C one.
 */
static int __hdt_strcmp(char *s1, char *s2, u32_t len1, u32_t len2)
{
  if (len1 != len2)
    return 0;

  if (len1 == 0)
    return 0;

  while (len1-- > 0)
    if (*s1++ != *s2++)
      return 0;

  return 1;
}

static void __hdt_bzero(char *s, u32_t len)
{
  while(len-- > 0)
    *s++ = '\0';
}

static void __hdt_memcpy(char *dst, char *src, u32_t len)
{
  if (len == 0)
    return;

  while (len-- > 0)
    *dst++ = *src++;
}


/*
 * HDT Entry Handlers
 */
static int hdt_entry_cpu(hdt_entry_header_t *entry)
{
  return 0;
}

static int hdt_entry_memory(hdt_entry_header_t *entry)
{
  hdt_entry_memory_t *memory_entry = (hdt_entry_memory_t *)entry;
  memory_size = memory_entry->e_size;

  return 0;
}

static void __copy_arg_value(char *dst, u32_t *length, hdt_entry_argument_t *entry)
{
  char *value = (char *)&entry->e_value;
  u32_t value_length = (u32_t)entry->e_value_length;
  u32_t len = (HDT_ARGUMENT_VALUE_LEN > value_length ? value_length : HDT_ARGUMENT_VALUE_LEN);

  __hdt_bzero(dst, HDT_ARGUMENT_VALUE_LEN + 1);
  __hdt_memcpy(dst, value, len);
  *length = len;
}

static int hdt_entry_argument(hdt_entry_header_t *entry)
{
  hdt_entry_argument_t *argument_entry = (hdt_entry_argument_t *)entry;
  char *name = (char *)&argument_entry->e_name;
  u32_t name_length = (u32_t)argument_entry->e_name_length;

  if (__hdt_strcmp("test-mode", name, 9, name_length)) {
    var_TEST_MODE = *(u32_t *)&argument_entry->e_value;
    return 0;
  }

#define device_argument(_dev_name, _dev_name_length, _var_name, _var_len_name)       \
  if (__hdt_strcmp(_dev_name, name, _dev_name_length, name_length)) {                \
    __copy_arg_value(_var_name, &_var_len_name, argument_entry);                     \
    return 0;                                                                        \
  }

  device_argument("rtc-device", 10, rtc_device_name, rtc_device_name_length);
  device_argument("tty-device", 10, tty_device_name, tty_device_name_length);
  device_argument("kbd-device", 10, kbd_device_name, kbd_device_name_length);

#undef device_argument

  return ERR_UNHANDLED_ARGUMENT;
}

static int hdt_entry_device(hdt_entry_header_t *entry)
{
  hdt_entry_device_t *device_entry = (hdt_entry_device_t *)entry;
  char *name = (char *)&device_entry->e_name;
  u32_t name_length = (u32_t)device_entry->e_name_length;

  if (__hdt_strcmp(rtc_device_name, name, rtc_device_name_length, name_length)) {
    hdt_entry_device_rtc_t *rtc_device = (hdt_entry_device_rtc_t *)device_entry;

    rtc_mmio_address = rtc_device->e_mmio_address;
    return 0;
  }

  if (__hdt_strcmp(tty_device_name, name, tty_device_name_length, name_length)) {
    hdt_entry_device_tty_t *tty_device = (hdt_entry_device_tty_t *)device_entry;

    tty_mmio_address = tty_device->e_mmio_address;
    return 0;
  }

  if (__hdt_strcmp(kbd_device_name, name, kbd_device_name_length, name_length)) {
    hdt_entry_device_kbd_t *kbd_device = (hdt_entry_device_kbd_t *)device_entry;

    kbd_mmio_address = kbd_device->e_mmio_address;
    return 0;
  }

  return 0;
}

/*
 * Parse HDT, extract necessary information, and store it in already existing
 * variables, provided by the assembly parth of FORTH kernel.
 * Returns 0 if everything went well, otherwise -1 is returned.
 */
int process_hdt(u8_t *hdt)
{
  hdt_header_t *header;

  header = (hdt_header_t *)hdt;

  if (header->h_magic != HDT_HEADER_MAGIC)
    return ERR_MALFORMED_HDT;

  if (header->h_entries == 0)
    return 0;

  hdt += sizeof(*header);

  while(header->h_entries-- > 0) {
    int ret;
    hdt_entry_header_t *entry = (hdt_entry_header_t *)hdt;
    hdt_entry_handler entry_handler = NULL;

    switch(entry->h_type) {
      case HDT_ENTRY_CPU:
        entry_handler = hdt_entry_cpu;
        break;
      case HDT_ENTRY_MEMORY:
        entry_handler = hdt_entry_memory;
        break;
      case HDT_ENTRY_ARGUMENT:
        entry_handler = hdt_entry_argument;
        break;
      case HDT_ENTRY_DEVICE:
        entry_handler = hdt_entry_device;
        break;
      default:
        break;
    }

    if (entry_handler == NULL)
      return ERR_MALFORMED_HDT;

    if ((ret = entry_handler(entry)) != 0)
      return ERR_MALFORMED_HDT;

    hdt += entry->h_length;
  }

  return 0;
}
