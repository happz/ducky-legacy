.include "defs.asm"


.macro VIRTUAL_IRQ index:
  .text

irq_routine_#index:
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
; Keyboard
;
irq_routine_1:
  retint

;
; Halt VM
;
irq_routine_32:
  hlt r0

$VIRTUAL_IRQ $INT_BLOCKIO
$VIRTUAL_IRQ $INT_VMDEBUG
$VIRTUAL_IRQ $INT_CONIO
$VIRTUAL_IRQ $INT_MM
$VIRTUAL_IRQ $IMT_MATH
