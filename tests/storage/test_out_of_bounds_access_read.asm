  .include "bio.asm"

  .text

  ; reset storage
  li r10, $BIO_SRST
  outw $BIO_PORT_STATUS, r10
  inw r0, $BIO_PORT_STATUS

  ; set storage ID
  li r10, 0x01
  outw $BIO_PORT_SID, r10
  ; set block ID
  la r10, 0xFF
  outw $BIO_PORT_BLOCK, r10
  ; set number of blocks
  li r10, 0x01
  outw $BIO_PORT_COUNT, r10
  ; set buffer address
  li r10, 0x00
  outw $BIO_PORT_ADDRESS, r10

  ; get status
  inw r1, $BIO_PORT_STATUS

  ; execute
  li r10, $BIO_DMA
  or r10, $BIO_READ
  outw $BIO_PORT_STATUS, r10

  ; get status again
  inw r2, $BIO_PORT_STATUS

  hlt 0x00
