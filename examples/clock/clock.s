.include "arch/ducky.hs"
.include "arch/rtc.hs"
.include "arch/svga.hs"

.def FG:               0x0400

.macro INSERT_DOT:
  li r1, 46
  stb r0, r1
  inc r0
.end

.macro INSERT_SPACE:
  li r1, 32
  stb r0, r1
  inc r0
.end

.macro INSERT_COLON:
  li r1, 58
  stb r0, r1
  inc r0
.end

.macro INSERT_CHR chr:
  li r1, #chr
  stb r0, r1
  inc r0
.end

.macro INSERT_DIGITS reg:
  mov r1, #reg
  call &print_digits
.end


  .data

  .type stack, space
  .space 64

  .type iteration, int
  .int 50

  .type second, byte
  .byte 255


  .text

main:
  li r0, $RTC_MMIO_ADDRESS
  add r0, $RTC_MMIO_FREQ
  li r1, 5
  stb r0, r1

  ; interrupts are disabled, there are no interrupt routines
  li r0, 0x00
  la r1, &irq_routine
  stw r0, r1
  add r0, $INT_SIZE
  la r1, &stack
  add r1, 64
  stw r0, r1

  ; OK, we're ready, enable interrupts and elts go
  sti

.loop:
  idle
  j &.loop
  hlt 0x00


  ;
  ; void print_digits(void *buff, int n)
  ;

print_digits:
  push r2
  mov r2, r1

  div r1, 10
  mod r2, 10
  add r1, 48
  add r2, 48

  stb r0, r1
  inc r0
  stb r0, r2
  inc r0

  pop r2

  ret

irq_routine:
  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_SECOND
  lb r9, r10

  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_MINUTE
  lb r8, r10

  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_HOUR
  lb r7, r10

  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_DAY
  lb r6, r10

  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_MONTH
  lb r5, r10

  li r10, $RTC_MMIO_ADDRESS
  add r10, $RTC_MMIO_YEAR
  lb r4, r10

  li r0, &second
  lb r0, r0
  cmp r0, r9
  be &__quit

__redraw:
  ; save new value
  li r0, &second
  stb r0, r9

  ; frame buffer address
  li r10, 0xA000

  ; update frame buffer
  mov r0, r10
  add r0, 16
  li r1, 0

  ; clear frame buffer
__memreset_loop:
  stb r0, r1
  dec r0
  cmp r0, r10
  bne &__memreset_loop

  ; write new values
  mov r0, r10

  $INSERT_DIGITS r6 ; day
  $INSERT_DOT
  $INSERT_SPACE
  $INSERT_DIGITS r5 ; month
  $INSERT_DOT
  $INSERT_SPACE
  $INSERT_CHR 50    ; century
  $INSERT_CHR 48
  $INSERT_DIGITS r4 ; year
  $INSERT_SPACE
  $INSERT_DIGITS r7 ; hours
  $INSERT_COLON
  $INSERT_DIGITS r8 ; minutes
  $INSERT_COLON
  $INSERT_DIGITS r9 ; seconds

  ; refresh screen
  li r0, $VGA_MMIO_ADDRESS
  add r0, $VGA_MMIO_COMMAND
  li r1, $VGA_CMD_REFRESH
  sts r0, r1

__quit:
  la r0, &iteration
  lw r1, r0
  dec r1
  bz &__halt
  stw r0, r1

  retint

__halt:
  hlt 0x00
