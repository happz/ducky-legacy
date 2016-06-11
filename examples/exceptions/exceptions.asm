.include "ducky.asm"
.include "tty.asm"
.include "boot.asm"

  .data

  .type __stack, space
  .space $PAGE_SIZE

  .type __exc_stack, space
  .space $PAGE_SIZE


  .section .rodata

  .type dummy_message, string
  .string "Unhandled exception\r\n"

  .type divide_by_zero_message, string
  .string "Divide by zero attempted\r\n"

  .type unaligned_access_message, string
  .string "Unaligned access attempted\r\n"

  .align 2
  .type __unaligned_memory_access_1, byte
  .byte 0x00
  .type __unaligned_memory_access_2, byte
  .byte 0x00

  .text

_entry:
  j &main


__putc:
  push r1
  li r1, $TTY_MMIO_ADDRESS
  add r1, $TTY_MMIO_DATA
  stb r1, r0
  pop r1
  ret


__puts:
  push r1
  push r2
  mov r2, r0
  li r0, $TTY_MMIO_ADDRESS
  add r0, $TTY_MMIO_DATA
__puts_loop:
  lb r1, r2
  bz &__puts_quit
  stb r0, r1
  inc r2
  j &__puts_loop
__puts_quit:
  pop r2
  pop r1
  ret


__exc_dummy:
  push r0
  la r0, &dummy_message
  call &__puts
  pop r0
  retint


__exc_divide_by_zero:
  push r0
  la r0, &divide_by_zero_message
  call &__puts
  pop r0
  add sp, $WORD_SIZE
  retint


__exc_unaligned_access:
  push r0
  la r0, &unaligned_access_message
  call &__puts
  pop r0
  add sp, $WORD_SIZE
  retint


main:
  la sp, &__stack
  add sp, $PAGE_SIZE

  li r0, $BOOT_IVT_ADDRESS
  mov r1, r0
  add r1, $PAGE_SIZE
  la r2, &__exc_dummy
  la r3, &__exc_stack
  add r3, $PAGE_SIZE

__exc_init_loop:
  stw r0, r2
  add r0, $WORD_SIZE
  stw r0, r3
  add r0, $WORD_SIZE
  cmp r0, r1
  bne &__exc_init_loop

  li r0, $BOOT_IVT_ADDRESS
  li r1, $EXCEPTION_DIVIDE_BY_ZERO
  mul r1, 8 ; two words per entry
  add r0, r1
  la r1, &__exc_divide_by_zero
  stw r0, r1

  li r0, $BOOT_IVT_ADDRESS
  li r1, $EXCEPTION_UNALIGNED_ACCESS
  mul r1, 8
  add r0, r1
  la r1, &__exc_unaligned_access
  stw r0, r1


  ; Hardware slots
  li r0, 0x00
  li r1, 16
__exc_loop:
  int r0
  inc r0
  cmp r0, r1
  bne &__exc_loop

  ; Exceptions

  ; InvalidOpcode
  int $EXCEPTION_INVALID_OPCODE

  ; InvalidInstSet
  int $EXCEPTION_INVALID_INST_SET

  ; DivideByZero
  li r0, 0x79
  div r0, 0x00

  ; UnalignedAccess
  la r0, &__unaligned_memory_access_2
  ls r0, r0

  ; PrivilegedInstr
  int $EXCEPTION_PRIVILEGED_INST

  ; DoubleFault
  int $EXCEPTION_DOUBLE_FAULT

  ; MemoryAccess
  int $EXCEPTION_MEMORY_ACCESS

  ; RegisterAccess
  int $EXCEPTION_REGISTER_ACCESS

  ; InvalidException
  int $EXCEPTION_INVALID_EXCEPTION

  ; CoprocessorError
  int $EXCEPTION_COPROCESSOR_ERROR

  hlt 0x00
