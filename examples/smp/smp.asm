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

  .type ap_running, int
  .int 0x00000000

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
; It's possible to use stack, there's still the one boot loader set up for primary core.
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
  la r2, &__secondary_thread           ; IP
  stw r1, r2
  add r1, $WORD_SIZE

  ; from now on, r1 points to CWT SP field, since IP does not change

  ; find HDT CPU entry
  li r2, $BOOT_HDT_ADDRESS

  ; check HDT header magic
  lw r3, r2
  li r4, 0x6F70
  liu r4, 0x4D5E
  cmp r3, r4
  bne &__secondary_wake_up_finished

  ; load number of entries
  add r2, $INT_SIZE
  lw r3, r2                            ; r3 counts number of entries left

  add r2, $INT_SIZE                    ; point to first entry
  li r4, $HDT_ENTRY_CPU

__find_hdt_entry_loop:
  ; no more entries? fail...
  cmp r3, 0
  bz &__secondary_wake_up_finished

  ; check entry type for searched type
  ls r5, r2
  cmp r5, r4
  be &__process_hdt_entry

  ; decrement number of entries to check
  dec r3
  ; load entry length
  add r2, $SHORT_SIZE
  ls r5, r2
  ; and add it (without the type field) to our entry pointer
  sub r5, $SHORT_SIZE
  add r2, r5
  j &__find_hdt_entry_loop

__process_hdt_entry:
  ; get number of CPUs and cores
  add r2, $HDT_ENTRY_PAYLOAD_OFFSET
  ls r3, r2                            ; # of CPUs
  add r2, $SHORT_SIZE
  ls r4, r2                            ; # of cores

  li r8, $BOOT_CWT_ADDRESS             ; init first secondary SP
  add r8, $PAGE_SIZE
  add r8, $PAGE_SIZE

  ; loop over all CPUs and cores, and wake them up
  li r5, 0 ; CPU counter
__secondary_wake_up_cpu_loop:
  cmp r5, r3 ; are we finished with CPUs?
  be &__secondary_wake_up_finished

  li r6, 0 ; CORE counter
__secondary_wake_up_core_loop:
  cmp r6, r4 ; are we finished with cores?
  be &__secondary_wake_up_cpu_loop_next

  ; compute CPUID
  mov r2, r5
  shiftl r2, 16
  or r2, r6

  ; core #0:#0 is primary core - this core.
  cmp r2, 0
  bz &__secondary_wake_up_core_loop_next

  mov r7, r1                           ; re-use our cached pointer
  ; find new stack
  stw r7, r8
  add r8, $PAGE_SIZE
  add r7, $WORD_SIZE
  la r9, &ap_running
  li r10, 0x0000
  stw r9, r10
  stw r7, r9

  ipi r2, 31 ; here should be some special interrupt number...

__secondary_wait_loop:
  lw r9, r7
  bz &__secondary_wait_loop

__secondary_wake_up_core_loop_next:
  inc r6
  j &__secondary_wake_up_core_loop

__secondary_wake_up_cpu_loop_next:
  inc r5
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
; void __secondary_thread(u32_t cpuid, u32_t *flag) __attribute__ ((noreturn))
;
; Address of this routine is placed into CWT slots, therefore this is what
; secondary cores do when primary one wakes them up.
;
; Do *something*, pretend there's a work to do till machine halts.
;
__secondary_thread:
  ; there's nothing to setup, so pretend there's something to do
  li r2, 0xFF
__secondary_thread_setup_loop:
  dec r2
  bnz &__secondary_thread_setup_loop

  ; now, signal primary it can launch another core
  li r2, 0xFFFF
  liu r2, 0xFFFF
  stw r1, r2

  ; we should not get any interrupts at all, so lets enable them
  sti

  ; and now spin and increace counter till machine halts
  li r2, 0xFFF
__secondary_thread_loop:
  dec r2
  bnz &__secondary_thread_loop

  hlt r0
