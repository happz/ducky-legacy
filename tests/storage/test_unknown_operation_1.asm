.def INT_BLOCKIO: 1

main:
  li r0, 1
  li r1, 79
  int $INT_BLOCKIO
  int 0
