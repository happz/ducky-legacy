.def VGA_BUFF:         0xA000
.def VGA_COMMAND_PORT: 0x03F0
.def VGA_DATA_PORT:    0x03F1

.def RTC_PORT_FREQ:    0x0300
.def RTC_PORT_SEC:     0x0301
.def RTC_PORT_MIN:     0x0302
.def RTC_PORT_HOUR:    0x0303
.def RTC_PORT_DAY:     0x0304
.def RTC_PORT_MONTH:   0x0305
.def RTC_PORT_YEAR:    0x0306

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

.include "defs.asm"


  .data

  .type iteration, int
  .int 50


  .text

print_digits:
  ; r0 - buff
  ; r1 - value
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

irq_routine_0:
  inb r9, $RTC_PORT_SEC
  inb r8, $RTC_PORT_MIN
  inb r7, $RTC_PORT_HOUR
  inb r6, $RTC_PORT_DAY
  inb r5, $RTC_PORT_MONTH
  inb r4, $RTC_PORT_YEAR

  ; update frame buffer
  li r0, $VGA_BUFF
  add r0, 16
  li r1, 0
.__memreset_loop:
  stb r0, r1
  dec r0
  cmp r0, $VGA_BUFF
  bne &.__memreset_loop

  li r0, $VGA_BUFF

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
  li r0, 0x0002
  out $VGA_COMMAND_PORT, r0

  li r0, &iteration
  lw r1, r0
  dec r1
  bz &halt
  stw r0, r1

  retint

halt:
  li r0, 0
  hlt r0


main:
  li r0, 5
  outb $RTC_PORT_FREQ, r0

.loop:
  idle
  j &.loop
  int 0
