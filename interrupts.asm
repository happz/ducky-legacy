.def PORT_STDOUT: 0x100

.def PORT_DISK_CMD:  0x200
.def PORT_DISK_DATA: 0x202

  .type jiffies, int
  .int 0

  .type message, string
  .string "Ping!"

irq_timer:
  push r0
  push r1
  li r0, &jiffies
  lw r1, r0
  inc r1
  stw r0, r1
  pop r1
;  li r0, &message
;  call &writesn
  pop r0
  retint

irq_conio:
  ; NOP - just wake up all sleepers waiting for console IO
  retint

int_halt:
  hlt r0

int_read_blocks:
  ; r0 ... device id
  ; r1 ... src ptr low 16
  ; r2 ... src ptr high 16
  ; r3 ... dst ptr
  ; r4 ... number of blocks
  push r5 ; operation handle
  push r6 ; driver reply
.int_read_blocks_acquire_slot:
  in r5, $PORT_DISK_CMD
  cmp r5, r5
  bz &.int_read_blocks_acquire_slot
  li r6, 0
  out $PORT_DISK_DATA, r6 ; read/write
  out $PORT_DISK_DATA, r0 ; device id
  out $PORT_DISK_DATA, r1 ; src ptr low 16
  out $PORT_DISK_DATA, r2 ; src ptr high 16
  out $PORT_DISK_DATA, r3 ; dst ptr
  lw r6, fp[36]
  out $PORT_DISK_DATA, r6 ; dst ds
  out $PORT_DISK_DATA, r4 ; cnt
.int_read_blocks_release_slot:
  in r6, $PORT_DISK_DATA
  cmp r5, r6
  bne &.int_read_blocks_release_slot
  pop r6
  pop r5
  retint

int_write_blocks:
  ; r0 ... device id
  ; r1 ... src ptr
  ; r2 ... dst ptr low 16
  ; r3 ... dst ptr high 8
  ; r4 ... number of blocks
  push r5
  push r6
.int_write_blocks_acquire_slot:
  in r5, $PORT_DISK_CMD
  cmp r5, r5
  bz &.int_write_blocks_acquire_slot
  li r6, 1
  out $PORT_DISK_DATA, r6 ; read/write
  out $PORT_DISK_DATA, r0 ; device id
  out $PORT_DISK_DATA, r1 ; src ptr
  lw r6, fp[38]
  out $PORT_DISK_DATA, r6 ; src ds
  out $PORT_DISK_DATA, r1 ; dst ptr low 16
  out $PORT_DISK_DATA, r2 ; dst ptr high 16
  out $PORT_DISK_DATA, r4 ; cnt
.int_write_blocks_release_slot:
  in r6, $PORT_DISK_DATA
  cmp r5, r6
  bne &.int_write_blocks_release_slot
  pop r6
  pop r5
  retint

writeln:
  # > r0: string address
  push r1
.__writeln_loop:
  lb r1, r0
  bz &.__writeln_crlf
  outb $PORT_STDOUT, r1
  inc r1
  j &.__writeln_loop
.__writeln_crlf:
  li r1, 0xA
  outb $PORT_STDOUT, r1
  li r1, 0xD
  outb $PORT_STDOUT, r1
  pop r1
  ret
