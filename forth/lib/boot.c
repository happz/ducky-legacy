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
 * +--------------------+ <- 0x00000700
 * | RTC MMIO           |
 * +--------------------+ <- 0x00000800
 * | Kbd MMIO           |
 * +--------------------+ <- 0x00000900
 * | TTY MMIO           |
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

ASM_INT(u32_t, rstack_top);
ASM_INT(u32_t, var_HEAP);
ASM_INT(u32_t, var_HEAP_START);
ASM_INT(u32_t, var_SZ);
ASM_INT(u32_t, var_EVT);

static u32_t __mm_evt, __mm_heap, __mm_rtc_esr_sp, __mm_kbd_esr_sp, __mm_failsafe_esr_sp, __mm_rsp, __mm_sp;

static void init_memory(void)
{
  u32_t memory_size = CONFIG_RAM_SIZE;

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

// Exception service routines implemented in assembly - our clang clone
// does not support inline assembly yet, and we need retint to return these.
extern void rtc_esr(void);
extern void nop_esr(void);

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

  for(header = (word_header_t *)var_LATEST; header != NULL; header = header->wh_link)
    header->wh_name_crc = cs_crc(&header->wh_name);
}

void do_boot_phase2(void)
{
  init_memory();
  init_evt();
  init_crcs();

  // Setup RTC frequency
  *(u8_t *)(CONFIG_RTC_MMIO_BASE + RTC_MMIO_FREQ) = RTC_FREQ;
}
