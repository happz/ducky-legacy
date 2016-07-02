  .include "bio.asm"

  .text

  li r12, $BIO_MMIO_ADDRESS

.macro bio_send port:
  mov r11, r12
  add r11, #port
  stw r11, r10
.end

.macro bio_receive port, reg:
  mov r11, r12
  add r11, #port
  lw #reg, r11
.end

  ; reset storage
  li r10, $BIO_SRST
  $bio_send $BIO_MMIO_STATUS
  lw r0, r11

  ; set storage ID
  li r10, 0x08
  $bio_send $BIO_MMIO_SID

  ; get status
  $bio_receive $BIO_MMIO_STATUS, r1

  li r11, 0x00
  li r12, 0x00

  hlt 0x00
