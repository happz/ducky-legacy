.include "ducky.asm"
.include "boot.asm"
.include "control.asm"
.include "hdt.asm"
.include "bio.asm"


  .data

  ; Initial stack
  .type init_stack, space
  .space $PAGE_SIZE

  .text

  ; get our CPUID
  ctr r0, $CONTROL_CPUID
  bnz &__secondary_boot
  j &__primary_boot

  ; should not return, just in case
  hlt 0xFFFF


;
; void __load_blocks(u32_t storage, u32_t block, u32_t cnt, void *buff)
;
__load_blocks:
  push r10

  ; reset storage
  li r10, $BIO_SRST
  outw $BIO_PORT_STATUS, r10

  ; set storage ID
  outw $BIO_PORT_SID, r0

  ; set block ID
  outw $BIO_PORT_BLOCK, r1

  ; set number of blocks
  outw $BIO_PORT_COUNT, r2

  ; set buffer address
  outw $BIO_PORT_ADDRESS, r3

  ; execute
  li r10, $BIO_DMA
  or r10, $BIO_READ
  outw $BIO_PORT_STATUS, r10

__load_blocks_wait:
  inw r10, $BIO_PORT_STATUS
  and r10, $BIO_RDY
  bz &__load_blocks_wait

  pop r10
  ret


;
; void __primary_boot(u32_t cpuid) __attribute__ ((noreturn))
;
; Boot primary core - prepare some structures, and load next phase.
;
__primary_boot:
  mov r27, r0

  ; use our initial stack
  la sp, &init_stack
  add sp, $PAGE_SIZE
  mov fp, sp

  ; clear IVT
  li r0, $BOOT_IVT_ADDRESS
  li r1, $PAGE_SIZE
  call &memzero

  ; clear CWT
  li r0, $BOOT_CWT_ADDRESS
  li r1, $PAGE_SIZE
  call &memzero

  ;
  ; Load next phase
  ;
  ; Hic sunt binary loading, from block device, or from FLASH memory, or ROM...
  ;

  la r26, &__primary_boot_halt

.ifdef BOOT_IMAGE
  ; load image from storage #0

  li r0, 0x00
  li r1, 0x00
  li r2, 0x01
  li r3, $BOOT_OS_ADDRESS
  call &__load_blocks

  li r0, 0x00
  li r1, 0x01
  li r3, $BOOT_OS_ADDRESS
  lw r2, r3
  dec r2
  call &__load_blocks

  li r26, $BOOT_OS_ADDRESS
.endif

  ; cpuid is the first argument
  mov r0, r27 ; cpuid is the first argument
  j r26       ; and jump to the next phase

  ; it should never return, but just in case
  hlt 0xFF

__primary_boot_halt:
  hlt 0xFFFFF


;
; void __secondary_boot(u32_t cpuid) __attribute__ ((noreturn))
;
; Boot secondary core - fall asleep, and wait for primary core to tell us where
; to jump, by sending IPI to wake us up.
;
__secondary_boot:
  mov r27, r0

  ; get our CWT slot
  mov r1, r0
  li r0, $BOOT_HDT_ADDRESS
  call &__core_get_cwt_slot

  ; sleep and wait pro primary core to wake us up
  idle

  ; in our CWT slot is now address we are supposed to jump to
  lw r1, r0

  ; pass CPUID as a first argument
  mov r0, r27

  ; and jump to our new thread
  j r1

  ; it should never return, but just in case
  hlt 0xFF
