.include "defs.asm"


.macro VIRTUAL_IRQ index:
  .text

irq_routine_#index:
  retint
.end

.macro VIRTUAL_INTERRUPT index:
  .text

int_routine_#index:
  retint
.end


  .data

  .type jiffies, int
  .int 0

  .text

;
; Timer
;
; Increment jiffies counter, nothing else to do
;
irq_routine_0:
  push r0
  push r1
  li r0, &jiffies
  lw r1, r0
  inc r1
  stw r0, r1
  pop r1
  pop r0
  retint

;
; Console IO
;
; Just wake up all sleepers waiting for console IO
;
$VIRTUAL_IRQ 1

;
; Halt VM
;
int_routine_0:
  hlt r0

;
; Block IO
;
int_routine_1:
  ; r0 ... direction - 0 read, 1 write
  ;
  ; All:
  ; r1 ... device id
  ; r5 ... number of blocks
  ;
  ; Read:
  ; r2 ... src ptr low 16
  ; r3 ... src ptr high 16
  ; r4 ... dst ptr
  ;
  ; Write
  ; r2 ... src ptr
  ; r3 ... dst ptr low 16
  ; r4 ... dst ptr high 8
  ;
  push r6 ; operation handle
  push r7 ; driver reply
.int_blockio_acquire_slot:
  in r6, $PORT_BLOCKIO_CMD
  cmp r6, r6
  bz &.int_blockio_acquire_slot

  cmp r0, 1
  bz &.int_blockio_request_write

.int_blockio_request_read:
  li r7, 0
  out $PORT_BLOCKIO_DATA, r7 ; read/write
  out $PORT_BLOCKIO_DATA, r1 ; device id
  out $PORT_BLOCKIO_DATA, r2 ; src ptr low 16
  out $PORT_BLOCKIO_DATA, r3 ; src ptr high 16
  out $PORT_BLOCKIO_DATA, r4 ; dst ptr
  lw r7, fp[36]
  out $PORT_BLOCKIO_DATA, r7 ; dst ds
  out $PORT_BLOCKIO_DATA, r5 ; cnt
  j &.int_blockio_release_slot

.int_blockio_request_write:
  li r6, 1
  out $PORT_BLOCKIO_DATA, r6 ; read/write
  out $PORT_BLOCKIO_DATA, r0 ; device id
  out $PORT_BLOCKIO_DATA, r1 ; src ptr
  lw r6, fp[38]
  out $PORT_BLOCKIO_DATA, r6 ; src ds
  out $PORT_BLOCKIO_DATA, r1 ; dst ptr low 16
  out $PORT_BLOCKIO_DATA, r2 ; dst ptr high 16
  out $PORT_BLOCKIO_DATA, r4 ; cnt

.int_blockio_release_slot:
  in r7, $PORT_BLOCKIO_DATA
  cmp r6, r7
  bne &.int_blockio_release_slot
  pop r7
  pop r6
  retint


;
; VM debug logging virtual interrupt
;
$VIRTUAL_INTERRUPT $INT_VMDEBUG
$VIRTUAL_INTERRUPT $INT_CONIO
