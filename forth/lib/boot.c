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
ASM_INT(u32_t, __mm_heap);
ASM_INT(u32_t, __mm_rtc_esr_sp);
ASM_INT(u32_t, __mm_kbd_esr_sp);
ASM_INT(u32_t, __mm_failsafe_esr_sp);
ASM_INT(u32_t, __mm_rsp);
ASM_INT(u32_t, __mm_sp);
ASM_INT(u32_t, __mm_evt);

ASM_INT(u32_t, rstack_top);
ASM_INT(u32_t, var_HEAP);
ASM_INT(u32_t, var_HEAP_START);
ASM_INT(u32_t, var_SZ);
ASM_INT(u32_t, var_EVT);

// These variables will contain important information we got by parsing
// HDT - test-mode setting, and MMIO base addresses.
ASM_INT(u32_t, var_TEST_MODE);
ASM_INT(u32_t, memory_size);
ASM_INT(u32_t, rtc_mmio_address);
ASM_INT(u32_t, tty_mmio_address);
ASM_INT(u32_t, kbd_mmio_address);

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

  bzero(dst, HDT_ARGUMENT_VALUE_LEN + 1);
  __c_memcpy(dst, value, len);
  *length = len;
}

static char __hdt_argument_name_test_mode[] = "test-mode";
static char __hdt_argument_name_rtc_device[] = "rtc-device";
static char __hdt_argument_name_tty_device[] = "tty-device";
static char __hdt_argument_name_kbd_device[] = "kbd-device";

static int hdt_entry_argument(hdt_entry_header_t *entry)
{
  hdt_entry_argument_t *argument_entry = (hdt_entry_argument_t *)entry;
  char *name = (char *)&argument_entry->e_name;
  u32_t name_length = (u32_t)argument_entry->e_name_length;

  if (!__c_strcmp(__hdt_argument_name_test_mode, name, 9, name_length)) {
    var_TEST_MODE = *(u32_t *)&argument_entry->e_value;
    return 0;
  }

#define device_argument(_dev_name, _dev_name_length, _var_name, _var_len_name)       \
  if (!__c_strcmp(_dev_name, name, _dev_name_length, name_length)) {                \
    __copy_arg_value(_var_name, &_var_len_name, argument_entry);                     \
    return 0;                                                                        \
  }

  device_argument(__hdt_argument_name_rtc_device, 10, rtc_device_name, rtc_device_name_length);
  device_argument(__hdt_argument_name_tty_device, 10, tty_device_name, tty_device_name_length);
  device_argument(__hdt_argument_name_kbd_device, 10, kbd_device_name, kbd_device_name_length);

#undef device_argument

  return ERR_UNHANDLED_ARGUMENT;
}

static int hdt_entry_device(hdt_entry_header_t *entry)
{
  hdt_entry_device_t *device_entry = (hdt_entry_device_t *)entry;
  char *name = (char *)&device_entry->e_name;
  u32_t name_length = (u32_t)device_entry->e_name_length;

  if (!__c_strcmp(rtc_device_name, name, rtc_device_name_length, name_length)) {
    hdt_entry_device_rtc_t *rtc_device = (hdt_entry_device_rtc_t *)device_entry;

    rtc_mmio_address = rtc_device->e_mmio_address;
    return 0;
  }

  if (!__c_strcmp(tty_device_name, name, tty_device_name_length, name_length)) {
    hdt_entry_device_tty_t *tty_device = (hdt_entry_device_tty_t *)device_entry;

    tty_mmio_address = tty_device->e_mmio_address;
    return 0;
  }

  if (!__c_strcmp(kbd_device_name, name, kbd_device_name_length, name_length)) {
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

extern void __ERR_unhandled_exception(void) __attribute__((noreturn));
static void __failsafe_esr(void) __attribute__((noreturn));

static void __failsafe_esr(void)
{
  __ERR_unhandled_exception();
}

#define EXCEPTION_ROUTINE(_name, _id, _message) \
static void __esr_ ## _name (void) __attribute__((noreturn)); \
static void __esr_ ## _name () \
{ \
  static char __esr_msg_ ## _name[] = "\r\nERROR: " _message "\r\n"; \
  __ERR_die(__esr_msg_ ## _name, _id); \
}

EXCEPTION_ROUTINE(invalid_opcode, EXCEPTION_INVALID_OPCODE, "Invalid opcode")
EXCEPTION_ROUTINE(invalid_instruction_set, EXCEPTION_INVALID_INST_SET, "Invalid instruction set")
EXCEPTION_ROUTINE(divide_by_zero, EXCEPTION_DIVIDE_BY_ZERO, "Divide by zero")
EXCEPTION_ROUTINE(unaligned_access, EXCEPTION_UNALIGNED_ACCESS, "Unaligned access")
EXCEPTION_ROUTINE(privileged_instruction, EXCEPTION_PRIVILEGED_INST, "Privileged instruction")
EXCEPTION_ROUTINE(double_fault, EXCEPTION_DOUBLE_FAULT, "Double fault")
EXCEPTION_ROUTINE(invalid_memory_access, EXCEPTION_MEMORY_ACCESS, "Invalid memory access")
EXCEPTION_ROUTINE(invalid_register_access, EXCEPTION_REGISTER_ACCESS, "Invalid register access")
EXCEPTION_ROUTINE(invalid_exception, EXCEPTION_INVALID_EXCEPTION, "Invalid exception")
EXCEPTION_ROUTINE(coprocessor_error, EXCEPTION_COPROCESSOR_ERROR, "Coprocessor error")

static void init_evt(void)
{
  int i;
  evt_entry_t *evt = (evt_entry_t *)__mm_evt, *entry;

#define SET_ESR(_index, _esr, _stack) do { entry = &evt[_index]; entry->e_ip = (u32_t)_esr; entry->e_sp = _stack; } while(0)

  // Reset all EVT entries to point to our "failsafe" routine
  for (i = 0; i < EXCEPTION_COUNT; i++)
    SET_ESR(i, __failsafe_esr, __mm_failsafe_esr_sp);

  // Setup necessary EVT routines

  SET_ESR(RTC_IRQ, rtc_esr, __mm_rtc_esr_sp);
  SET_ESR(KBD_IRQ, nop_esr, __mm_failsafe_esr_sp);

  SET_ESR(EXCEPTION_INVALID_OPCODE, __esr_invalid_opcode, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_INVALID_INST_SET, __esr_invalid_instruction_set, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_DIVIDE_BY_ZERO, __esr_divide_by_zero, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_UNALIGNED_ACCESS, __esr_unaligned_access, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_PRIVILEGED_INST, __esr_privileged_instruction, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_DOUBLE_FAULT, __esr_double_fault, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_MEMORY_ACCESS, __esr_invalid_memory_access, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_REGISTER_ACCESS, __esr_invalid_register_access, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_INVALID_EXCEPTION, __esr_invalid_exception, __mm_failsafe_esr_sp);
  SET_ESR(EXCEPTION_COPROCESSOR_ERROR, __esr_coprocessor_error, __mm_failsafe_esr_sp);

#undef SET_ESR
}


//-----------------------------------------------------------------------------
// FORTH word names' CRCs
//-----------------------------------------------------------------------------

ASM_INT(u32_t, var_LATEST);

static void init_crcs(void)
{
  word_header_t *header;

  for(header = (word_header_t *)var_LATEST; header != NULL; header = header->wh_link) {
    //print_hex((u32_t)header); putc(' '); print_hex((u32_t)&header->wh_name.cs_str); putc(' '); print_hex(header->wh_name.cs_len); BR();
    //print_word_name(header);
    header->wh_name_crc = __c_strcrc(&header->wh_name.cs_str, header->wh_name.cs_len);
    //print_hex(header->wh_name_crc); BR();
  }
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
