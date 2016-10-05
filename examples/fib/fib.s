#define STACK_SIZE 4096

  .data

  .type stack, space, STACK_SIZE


  .text

main:
  la sp, stack
  add sp, STACK_SIZE

  li r0, 30
  call fib
  hlt 0x00

fib:
  // r0 - N
  cmp r0, 1
  be __fib_one
  cmp r0, 0x00
  be __fib_zero

  push r1
  push r2
  mov r1, r0

  dec r0
  call fib
  mov r2, r0

  mov r0, r1
  sub r0, 2
  call fib
  add r0, r2

  pop r2
  pop r1
  ret

__fib_zero:
  li r0, 0x00
  ret

__fib_one:
  li r0, 1
  ret


