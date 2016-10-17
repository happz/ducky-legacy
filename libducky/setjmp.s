/*
 * setjmp and longjmp implementation
 */

  .global setjmp

setjmp:
  // R0 contains buffer address, and will be used for return value.
  // Therefore we don't have to bother with it.
  stw r0[  4], r1
  stw r0[  8], r2
  stw r0[ 12], r3
  stw r0[ 16], r4
  stw r0[ 20], r5
  stw r0[ 24], r6
  stw r0[ 28], r7
  stw r0[ 32], r8
  stw r0[ 36], r9
  stw r0[ 40], r10
  stw r0[ 44], r11
  stw r0[ 48], r12
  stw r0[ 52], r13
  stw r0[ 56], r14
  stw r0[ 60], r15
  stw r0[ 64], r16
  stw r0[ 68], r17
  stw r0[ 72], r18
  stw r0[ 76], r19
  stw r0[ 80], r20
  stw r0[ 84], r21
  stw r0[ 88], r22
  stw r0[ 92], r23
  stw r0[ 96], r24
  stw r0[100], r25
  stw r0[104], r26
  stw r0[108], r27
  stw r0[112], r28
  stw r0[116], r29
  stw r0[120], fp
  stw r0[124], sp

  // Extract return address, and save it
  push r1
  lw r1, fp[4]
  stw r0[128], r1
  pop r1

  li r0, 0x00
  ret


  .global longjmp

longjmp:
  cmp r1, 0x00                         // if val is zero, force 1 as a return value. If not, just use it.
  bnz __longjmp_restore
  li r1, 0x01
__longjmp_restore:
  // Store return value to r0's slot, and "restore" it at the end.
  // We cannot use stack because we're going to change SP as well.
  stw r0[  0], r1

  // Skip r1, we're gonna need it later for restoring return address
  lw r2,  r0[  8]
  lw r3,  r0[ 12]
  lw r4,  r0[ 16]
  lw r5,  r0[ 20]
  lw r6,  r0[ 24]
  lw r7,  r0[ 28]
  lw r8,  r0[ 32]
  lw r9,  r0[ 36]
  lw r10, r0[ 40]
  lw r11, r0[ 44]
  lw r12, r0[ 48]
  lw r13, r0[ 52]
  lw r14, r0[ 56]
  lw r15, r0[ 60]
  lw r16, r0[ 64]
  lw r17, r0[ 68]
  lw r18, r0[ 72]
  lw r19, r0[ 76]
  lw r20, r0[ 80]
  lw r21, r0[ 84]
  lw r22, r0[ 88]
  lw r23, r0[ 92]
  lw r24, r0[ 96]
  lw r25, r0[100]
  lw r26, r0[104]
  lw r27, r0[108]
  lw r28, r0[112]
  lw r29, r0[116]
  lw fp,  r0[120]
  lw sp,  r0[124]

  // Restore return address
  lw r1,  r0[128]
  stw fp[4], r1

  // Now we can restore r1, and load return address from r0's slot
  lw r1, r0[  4]
  lw r0, r0[  0]
  ret
