/*
 * Functions related to the booting process of FORTH kernel.
 *
 * HDT, EVT, memory layout, ... Pretty much anything necessary to start
 * kernel - as long as it can be written in C. There's still some assembly
 * code in boot_phase2 functions needed to move on when the functions bellow
 * are done.
 *
 * Note: These functions are called from boot_phase2, and therefore
 * there's no need to bother with saving all registers functions touch.
 */

#include <types.h>
#include <arch/ducky.h>
#include <arch/rtc.h>
#include <arch/keyboard.h>
#include <arch/tty.h>
#include <arch/boot.h>

#include <forth.h>

// These variables contain addresses of different parts of memory layout
// the kernel sets up.
extern u32_t __mm_heap, __mm_rtc_esr_sp, __mm_kbd_esr_sp, __mm_failsafe_esr_sp, __mm_rsp, __mm_sp, __mm_evt;
extern u32_t rstack_top, var_HEAP, var_HEAP_START, var_SZ, var_EVT;

// These variables will contain important information we got by parsing
// HDT - test-mode setting, and MMIO base addresses.
extern u32_t var_TEST_MODE, memory_size, rtc_mmio_address, tty_mmio_address, kbd_mmio_address;

// Exception service routines implemented in assembly - our clang clone
// does not support inline assembly yet, and we need retint to return these.
extern void rtc_esr(void);
extern void nop_esr(void);


//-----------------------------------------------------------------------------
// HDT processing
//-----------------------------------------------------------------------------

extern void __ERR_malformed_HDT(void) __attribute__((noreturn));

typedef int (*hdt_entry_handler)(hdt_entry_header_t *);

// Internal storage for device names parsed from HDT
static char rtc_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t rtc_device_name_length = 0;

static char tty_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t tty_device_name_length = 0;

static char kbd_device_name[HDT_ARGUMENT_VALUE_LEN + 1];
static u32_t kbd_device_name_length = 0;


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

  __c_bzero(dst, HDT_ARGUMENT_VALUE_LEN + 1);
  __c_memcpy(dst, value, len);
  *length = len;
}

static int hdt_entry_argument(hdt_entry_header_t *entry)
{
  hdt_entry_argument_t *argument_entry = (hdt_entry_argument_t *)entry;
  char *name = (char *)&argument_entry->e_name;
  u32_t name_length = (u32_t)argument_entry->e_name_length;

  if (__c_strcmp("test-mode", name, 9, name_length)) {
    var_TEST_MODE = *(u32_t *)&argument_entry->e_value;
    return 0;
  }

#define device_argument(_dev_name, _dev_name_length, _var_name, _var_len_name)       \
  if (__c_strcmp(_dev_name, name, _dev_name_length, name_length)) {                \
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

  if (__c_strcmp(rtc_device_name, name, rtc_device_name_length, name_length)) {
    hdt_entry_device_rtc_t *rtc_device = (hdt_entry_device_rtc_t *)device_entry;

    rtc_mmio_address = rtc_device->e_mmio_address;
    return 0;
  }

  if (__c_strcmp(tty_device_name, name, tty_device_name_length, name_length)) {
    hdt_entry_device_tty_t *tty_device = (hdt_entry_device_tty_t *)device_entry;

    tty_mmio_address = tty_device->e_mmio_address;
    return 0;
  }

  if (__c_strcmp(kbd_device_name, name, kbd_device_name_length, name_length)) {
    hdt_entry_device_kbd_t *kbd_device = (hdt_entry_device_kbd_t *)device_entry;

    kbd_mmio_address = kbd_device->e_mmio_address;
    return 0;
  }

  return 0;
}

/*
 * Parse HDT, extract necessary information, and store it in already existing
 * variables, provided by the assembly parth of FORTH kernel.
 */
static void process_hdt(hdt_header_t *header)
{
  if (header->h_magic != HDT_HEADER_MAGIC)
    __ERR_malformed_HDT(); // does not return

  if (header->h_entries == 0)
    return;

  char *hdt = ((char *)header + sizeof(*header));

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
      __ERR_malformed_HDT(); // does not return

    if ((ret = entry_handler(entry)) != 0)
      __ERR_malformed_HDT(); // does not return

    hdt += entry->h_length;
  }
}


//-----------------------------------------------------------------------------
// Address space setup
//-----------------------------------------------------------------------------

/*
 * Address space layout should look like this:
 *
 * LPF - Last Page Frame, base address of the last page of memory
 *
 * +--------------------+ <- 0x00000000
 * | Initial EVT        |
 * | .text.boot         |
 * +--------------------+ <- 0x00000100
 * | HDT                |
 * + ...                +
 * |                    |
 * +--------------------+
 * ...
 * +--------------------+ <- 0x00000A00
 * | .text              |
 * + ...                +
 * |                    |
 * +--------------------+
 * ...
 * +--------------------+ <- HEAP, HEAP-START
 * | RTC ESR stack      |
 * +--------------------+
 * | KBD ESR stack      |
 * +--------------------+
 * | Failsafe ESR stack |
 * +--------------------+
 * | Return stack       |
 * +--------------------+ <- RSP
 * | Stack              |
 * +--------------------+ <- LPF; SP
 * | Our EVT            |
 * +--------------------+
 */

static void init_memory(void)
{
  // pf hold the current page frame, and serves as a reference point.
  u32_t pf = (memory_size & PAGE_MASK) - PAGE_SIZE;

  // Right now, PF equals LPF, and that's address of our new EVT.
  __mm_evt = pf;

  // It is also a SP, since the next page is our future stack.
  __mm_sp = pf;
  pf -= PAGE_SIZE;

  // Next page is return stack, and we're on top of it
  __mm_rsp = pf;
  pf -= PAGE_SIZE;

  // ESR stacks follow: failsafe, ...
  __mm_failsafe_esr_sp = pf;
  pf -= PAGE_SIZE;

  // ... KBD, ...
  __mm_kbd_esr_sp = pf;
  pf -= PAGE_SIZE;

  // ... and RTC.
  __mm_rtc_esr_sp = pf;
  pf -= PAGE_SIZE;

  // And we're at the end of the list, the rest of memory is heap.
  __mm_heap = pf;

  // Set corresponding FORTH variables
  rstack_top = __mm_rsp;
  var_SZ = __mm_sp;
  var_HEAP = var_HEAP_START = __mm_heap;
  var_EVT = __mm_evt;
}


//-----------------------------------------------------------------------------
// EVT setup
//-----------------------------------------------------------------------------

static void __failsafe_esr(void) __attribute__((noreturn));

static char __unhandled_irq_message[] = "\r\nERROR: $ERR_UNHANDLED_IRQ: Unhandled irq\r\n";

static void __failsafe_esr(void)
{
  __ERR_die(__unhandled_irq_message, ERR_UNHANDLED_IRQ);
}

static void init_evt(void)
{
  int i;
  evt_entry_t *evt = (evt_entry_t *)__mm_evt, *entry;

  // Reset all EVT entries to point to our "failsafe" routine
  for (i = 0; i < EXCEPTION_COUNT; i++) {
    entry = &evt[i];

    entry->e_ip = (u32_t)__failsafe_esr;
    entry->e_sp = __mm_failsafe_esr_sp;
  }

  // Setup necessary EVT routines

  // RTC
  entry = &evt[RTC_IRQ];
  entry->e_ip = (u32_t)rtc_esr;
  entry->e_sp = (u32_t)__mm_rtc_esr_sp;

  // Keyboard
  entry = &evt[KBD_IRQ];
  entry->e_ip = (u32_t)nop_esr;
  entry->e_sp = (u32_t)__mm_failsafe_esr_sp;
}


//-----------------------------------------------------------------------------
// FORTH word names' CRCs
//-----------------------------------------------------------------------------

extern u32_t var_LATEST;

static void init_crcs(void)
{
  forth_word_header_t *header;

  for(header = (forth_word_header_t *)var_LATEST; header != NULL; header = header->wh_link)
    header->wh_name_crc = __c_strcrc(&header->wh_name, header->wh_name_len);
}

void do_boot_phase2(void)
{
  process_hdt((hdt_header_t *)BOOT_HDT_ADDRESS);
  init_memory();
  init_evt();
  init_crcs();

  // Update MMIO addresses to point to data ports
  kbd_mmio_address += KBD_MMIO_DATA;
  tty_mmio_address += TTY_MMIO_DATA;

  // Setup RTC frequency
  *(u8_t *)(rtc_mmio_address + RTC_MMIO_FREQ) = RTC_FREQ;
}
