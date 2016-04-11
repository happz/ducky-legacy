  .data

  .type stack, space
  .space 256

  .text

main:
  la sp, &stack
  add sp, 4096

  li r0, 30
  call &fib
  hlt 0x00

fib:
  ; r0 - N
  cmp r0, 1
  be &__fib_one
  cmp r0, 0
  be &__fib_zero

  push r1
  push r2
  mov r1, r0

  dec r0
  call &fib
  mov r2, r0

  mov r0, r1
  sub r0, 2
  call &fib
  add r0, r2

  pop r2
  pop r1
  ret

__fib_zero:
  li r0, 0
  ret

__fib_one:
  li r0, 1
  ret


