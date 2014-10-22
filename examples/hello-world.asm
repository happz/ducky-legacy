data message, "Hello, world!"
main:
  loada r1, 14
  loada r2, &message
  loada r3, 0x100
loop:
  load r2, r4 b
  out r4, r3 b
  inc r2
  dec r1
  jnz loop
  loada r2, 10
  out r2, r3 b
  loada r2, 13
  out r2, r3 b
  loada r1, 0
  hlt r1

