  .include "bio.asm"

  .text

  ; reset storage
  li r10, $BIO_SRST
  outw $BIO_PORT_STATUS, r10

  inw r0, $BIO_PORT_STATUS

  ; set storage ID
  li r10, 0x08
  outw $BIO_PORT_SID, r10

  inw r1, $BIO_PORT_STATUS

  hlt 0x00
