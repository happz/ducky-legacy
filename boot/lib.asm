.include "ducky.asm"
.include "boot.asm"
.include "hdt.asm"

;
; void memset(void *ptr, u32_t length, u8_t byte)
;
; Set all bytes in area, starting at PTR and of length LENGTH, to BYTE.
;
  .global memset
memset:
  cmp r1, 0
__memset_loop:
  bz &__memset_finished
  stb r0, r2
  inc r0
  dec r1
  j &__memset_loop
__memset_finished:
  ret


;
; void memzero(void *ptr, u32_t length)
;
; Set all bytes in area, starting at PTR and of length LENGTH, to zero.
;
  .global memzero
memzero:
  push r2
  li r2, 0x00
  call &memset
  pop r2
  ret


;
; u32_t *__core_get_cwt_slot(HDTHeader *hdt, u32_t cpuid)
;
  .global __core_get_cwt_slot
__core_get_cwt_slot:
  push r2
  push r3

  push r1
  li r1, $HDT_ENTRY_CPU
  call &__find_hdt_entry
  pop r1

  cmp r0, 0x7FFF
  be &__core_get_cwd_slot_quit

  ; shift to nr_cores field...
  add r0, $SHORT_SIZE ; type
  add r0, $SHORT_SIZE ; length
  add r0, $SHORT_SIZE ; nr_cpus
  ; ... and fetch if
  ls r2, r0

  ; we have CPUID, we have number of cores per cpu, lets get our slot
  mov r3, r1        ; save CPUID for later
  shiftr r1, 16     ; get our "CPU" id
  mul r1, r2        ; multiply by number of CPUs
  mul r1, $INT_SIZE ; multiply by size of each slot
  shiftl r3, 16     ; get our "core" id
  shiftr r3, 16
  mul r3, $INT_SIZE ; multiply by size of each slot
  add r1, r3        ; add "core" offset to a "cpu" one
  add r1, $BOOT_CWT_ADDRESS ; and relocate it to correct starting address
  mov r0, r1

__core_get_cwd_slot_quit:
  pop r3
  pop r2
  ret


;
; HDTStructure *__find_hdt_entry(HDTHeader *hdt, u16_t type)
;
  .global __find_hdt_entry
__find_hdt_entry:
  push r2
  push r3

  ; check HDT header magic
  lw r2, r0
  li r3, 0x6F70
  liu r3, 0x4D5E
  cmp r2, r3
  bne &__find_hdt_entry_fail

  ; load number of entries
  add r0, $INT_SIZE
  lw r2, r0

  add r0, $INT_SIZE     ; point to first entry

__find_hdt_entry_loop:
  ; no more entries? fail...
  cmp r2, 0
  bz &__find_hdt_entry_fail

  ; check entry type for searched type
  ls r3, r0
  cmp r1, r3
  bne &__find_hdt_entry_next

  ; we got it, return
  pop r3
  pop r2
  ret

__find_hdt_entry_fail:
  pop r3
  pop r2
  li r0, 0xFFFF
  ret

__find_hdt_entry_next:
  ; decrement number of entries to check
  dec r2
  ; load entry length
  add r0, $SHORT_SIZE
  ls r3, r0
  ; and add it (without the type field) to our entry pointer
  sub r3, $SHORT_SIZE
  add r0, r3
  j &__find_hdt_entry_loop
