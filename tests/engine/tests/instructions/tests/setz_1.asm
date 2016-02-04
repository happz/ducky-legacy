  .text

  li r1, 0xFF
  li r2, 0xFF

  li r0, 1
  dec r0
  setz r1

  li r0, 1
  dec r0
  setnz r2

  hlt 0x00
