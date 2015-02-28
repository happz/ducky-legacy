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

$VIRTUAL_INTERRUPT $INT_BLOCKIO
$VIRTUAL_INTERRUPT $INT_VMDEBUG
$VIRTUAL_INTERRUPT $INT_CONIO
$VIRTUAL_INTERRUPT $INT_MM
$VIRTUAL_INTERRUPT $INT_MATH
