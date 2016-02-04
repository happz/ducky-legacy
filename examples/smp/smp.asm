.include "ducky.asm"
.include "control.asm"
.include "hdt.asm"
.include "boot.asm"
.include "rtc.asm"

  .data

  .type isr_stack, space
  .space $PAGE_SIZE

  .type jiffies, int
  .int 0

  .text

_entry:
  ; this is where the bootloader jumps to
  j &_start

  ; it should never return, but just in case
  hlt 0xFF


;
; void isr_rtc(void)
;
; RTC ISR - simply increases jiffies counter by one.
;
isr_rtc:
  push r0
  push r1
  la r0, &jiffies
  lw r1, r0
  inc r1
  stw r0, r1
  pop r1
  pop r0
  retint


;
; void isr_dummy(void)
;
; Dummy ISR - does nothing, it's only a placeholder for interrupts that need
; servicing but we don't care about them.
;
isr_dummy:
  retint


;
; void main(u32_t cpuid)
;
; Executed on primary core, all other cores are waiting for this process to let
; them know what to do next.
;
_start:
  ; set RTC frequency
  li r0, 2
  outb $RTC_PORT_FREQ, r0

  ; IVT was cleared by bootloader, lets get one routine for timer, and one
  ; dummy routine for all other interrupts.

  ; interrupt stack
  la r1, &isr_stack
  add r1, $PAGE_SIZE

  ; get IVT address
  ctr r2, $CONTROL_IVT

  ; this address is the first one *after* IVT
  mov r3, r2
  add r3, $PAGE_SIZE

  ; RTC ISR
  la r4, &isr_rtc
  stw r2, r4
  add r2, $WORD_SIZE
  stw r2, r1
  add r2, $WORD_SIZE

  ; dummy ISRs
  la r4, &isr_dummy
__ivt_copy_loop:
  stw r2, r4
  add r2, $WORD_SIZE
  stw r2, r1
  add r2, $WORD_SIZE
  cmp r2, r3
  be &__ivt_copy_finished
  j &__ivt_copy_loop

__ivt_copy_finished:

  ; setup CWT
  li r1, $BOOT_CWT_ADDRESS
  mov r2, r1
  add r2, $PAGE_SIZE

  la r3, &__secondary_thread

__cwt_init_loop:
  stw r1, r3
  add r1, $WORD_SIZE
  cmp r1, r2
  bne &__cwt_init_loop

  ; Now, when CWT is filled with vectors, lets wake up all secondary cores

  ; find HDT CPU entry
  li r0, $BOOT_HDT_ADDRESS
  li r1, $HDT_ENTRY_CPU
  call &__find_hdt_entry
  cmp r0, 0x7FFF
  be &__secondary_wake_up_finished

  ; get number of CPUs and cores
  add r0, $HDT_ENTRY_PAYLOAD_OFFSET
  ls r2, r0 ; # of CPUs
  add r0, $SHORT_SIZE
  ls r3, r0 ; # of cores

  ; loop over all CPUs and cores, and wake them up
  li r4, 0 ; CPU counter
__secondary_wake_up_cpu_loop:
  cmp r4, r2 ; are we finished with CPUs?
  be &__secondary_wake_up_finished

  li r5, 0 ; CORE counter
__secondary_wake_up_core_loop:
  cmp r5, r3 ; are we finished with cores?
  be &__secondary_wake_up_cpu_loop_next

  ; compute CPUID
  mov r1, r4
  shiftl r1, 16
  or r1, r5

  ; core #0:#0 is primary core - this core.
  cmp r1, 0
  bz &__secondary_wake_up_core_loop_next

  ipi r1, 31 ; here should be some special interrupt number...

__secondary_wake_up_core_loop_next:
  inc r5
  j &__secondary_wake_up_core_loop

__secondary_wake_up_cpu_loop_next:
  inc r4
  j &__secondary_wake_up_cpu_loop

__secondary_wake_up_finished:

  ; Now, all secondary cores are spinning their HW, and we are primarily done.
  ; It's time to enable interrupts, and do some real spinning too.
  sti

  li r1, 0xFFF
__primary_thread_loop:
  dec r1
  bnz &__primary_thread_loop

  hlt 0x00


;
; void __secondary_thread(u32_t cpuid) __attribute__ ((noreturn))
;
; Address fo this routine is placed into CWT slots, therefore this is what
; secondary cores do when primary one wakes them up.
;
; Do *something*, pretend there's a work to do till machine halts.
;
__secondary_thread:
  ; we should not get any interrupts at all, so lets enable them
  sti

  ; and now spin and increace counter till machine halts
  li r1, 0xFFF
__secondary_thread_loop:
  dec r1
  bnz &__secondary_thread_loop

  hlt r0
