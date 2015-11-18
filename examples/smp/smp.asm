.include "defs.asm"
.include "control.asm"
.include "hdt.asm"

.def CWT_BASE: 0x8000
.def CWT_SIZE: 32

  .section .cwt, rwbl
  .space $CWT_SIZE


  .data

  ; keep it at the beggining to have IVT page-aligned
  .type ivt_base, space
  .space $PAGE_SIZE


  .text

  .global main
main:
  sis $INST_SET_CONTROL
  ctr r1, $CONTROL_CPUID
  sis $INST_SET_DUCKY
  bnz &__secondary_boot
  j &__primary_boot

  ; should not return, just in case
  li r0, 0xFFFE
  int $INT_HALT


;
; Boot primary core
; Basically just wake up other cores and quit
;
__primary_boot:
  ; r0 - HDT
  ; r1 - CPUID

  ; setup IVT
  ; copy it first
  sis $INST_SET_CONTROL
  ; IVT segment
  ctr r3, $CONTROL_IVT_SEGMENT
  ; IVT address - src pointer
  ctr r4, $CONTROL_IVT_ADDRESS
  sis $INST_SET_DUCKY

  ; dst pointer
  li r5, &ivt_base
  ; stopper
  mov r6, r5
  add r6, $PAGE_SIZE

__ivt_copy_loop:
  cmp r5, r6
  be &__ivt_copy_finished
  lw r7, r3(r4)
  stw r5, r7
  add r4, 2
  add r5, 2
  j &__ivt_copy_loop

__ivt_copy_finished:

  ; save HDT base
  mov r12, r0

  ; find HDT CPU entry
  li r1, $HDT_ENTRY_CPU
  call &__find_hdt_entry
  cmp r0, 0xFFFF
  be &__primary_boot_fail

  ; get number of CPUs and CPU cores
  li r2, $HDT_SEGMENT ; HDT segment
  add r0, $HDT_ENTRY_PAYLOAD_OFFSET
  lw r3, r2(r0) ; r3 - nr_cpus
  add r0, 2
  lw r4, r2(r0) ; r4 - nr_cores

  ; loop over all cores, and prepare their first IPs
  li r5, 0 ; CPU counter
__primary_boot_cpu_loop:
  cmp r5, r3
  be &__primary_boot_secondary_finished

  li r6, 0 ; CORE counter
__primary_boot_core_loop:
  cmp r6, r4
  be &__primary_boot_core_loop_finished

  ; compute cpuid
  mov r1, r5
  shiftl r1, 8
  or r1, r6

  ; core #0:#0 is primary core - this core.
  cmp r1, 0
  bz &__primary_boot_core_loop_next

  push r1 ; save cpuid for later

  mov r0, r12
  call &__core_get_cwt_slot

  pop r1 ; restore cpuid

  cmp r0, 0xFFFF
  be &__primary_boot_fail

  ; fill CTW slot, and wake up the core
  li r7, &__secondary_thread
  stw r0, r7
  ipi r1, $INT_NOP

__primary_boot_core_loop_next:
  inc r6
  j &__primary_boot_core_loop

__primary_boot_core_loop_finished:
  inc r5
  j &__primary_boot_cpu_loop

__primary_boot_secondary_finished:
  ; we started all other cores, nothing else to do...
  li r0, 0

__primary_boot_fail:
  int $INT_HALT


;
; Secondary threads' job
;
__secondary_thread:
  ; r0 - HDT
  ; r1 - CPUID

  ; setup IVT
  li r2, &ivt_base
  cli
  sis $INST_SET_CONTROL
  ctw $CONTROL_IVT_SEGMENT, ds
  ctw $CONTROL_IVT_ADDRESS, r2
  sis $INST_SET_DUCKY
  sti

  ; just quit with our CPUID as exit value
  mov r0, r1
  add r0, 0x1000
  int $INT_HALT


;
; Boot secondary core
; Fall asleep, and wait for primary core to tell us where to jump
;
__secondary_boot:
  push r0 ; HDT
  push r1 ; CPUID

  ; get our CWT slot
  call &__core_get_cwt_slot

  ; sleep and wait pro primary core to wake us up
  idle

  ; in our CWT slot is now address we are supposed to jump to
  lw r3, r0

  ; clean stack
  pop r1
  pop r0

  ; and jump to our new thread
  j r3

  ; it should never return, but just in case
  li r0, 0xFFFE
  int $INT_HALT


__core_get_cwt_slot:
  ; r0 - HDT
  ; r1 - CPUID

  push r2
  push r3

  push r1
  li r1, 0x00
  call &__find_hdt_entry
  pop r1

  cmp r0, 0xFFFF
  be &__core_get_cwd_slot_quit

  li r2, 0x00 ; HDT segment

  add r0, 4 ; shift to nr_cores field
  lw r3, r2(r0) ; and fetch it

  ; we have CPUID, we have number of cores per cpu, lets get our slot
  push r1
  shiftr r1, 8
  mul r1, r3
  mul r1, 2
  pop r3
  and r3, 0xFF
  mul r3, 2
  add r1, r3
  add r1, $CWT_BASE
  mov r0, r1

__core_get_cwd_slot_quit:
  pop r3
  pop r2
  ret


__find_hdt_entry:
  ; r0 - HDT
  ; r1 - type

  push r2
  push r3
  push r4

  li r2, 0x00 ; r2 is segment register for reading HDT

  ; check HDT header magic
  lw r3, r2(r0)
  cmp r3, 0x4D5E
  bne &__find_hdt_entry_fail

  ; load number of entries
  add r0, 2
  lw r3, r2(r0)

  add r0, 2     ; point to first entry

__find_hdt_entry_loop:
  ; no more entries? fail...
  cmp r3, 0
  bz &__find_hdt_entry_fail

  ; check entry type for searched type
  lw r4, r2(r0)
  cmp r4, r1
  bne &__find_hdt_entry_next

  pop r4
  pop r3
  pop r2
  ret

__find_hdt_entry_fail:
  pop r4
  pop r3
  pop r2
  li r0, 0xFFFF
  ret

__find_hdt_entry_next:
  ; decrement number of entries to check
  dec r3
  ; load entry length
  add r0, 2
  lw r4, r2(r0)
  ; and add it (without the type filed) to our entry pointer 
  sub r4, 2
  add r0, r4
  j &__find_hdt_entry_loop
