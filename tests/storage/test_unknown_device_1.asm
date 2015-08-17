.def INT_BLOCKIO: 1
.def BLOCKIO_READ: 0

main:
  li r0, 7 ; there's no device with id 7...
  li r1, $BLOCKIO_READ
  int $INT_BLOCKIO
  int 0
