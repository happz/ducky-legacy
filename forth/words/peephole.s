#if (CONFIG_PEEPHOLE == 1)

DEFCODE("SI_LIT_0", 8, 0x00, SI_LIT_0)
  // ( -- 0 )
  push TOS
  li TOS, 0x00
  NEXT

DEFCODE("SI_LIT_1", 8, 0x00, SI_LIT_1)
  // ( -- 1 )
  push TOS
  li TOS, 0x01
  NEXT

DEFCODE("SI_LIT_2", 8, 0x00, SI_LIT_2)
  // ( -- 2 )
  push TOS
  li TOS, 0x02
  NEXT

DEFCODE("SI_LIT_FFFFFFFF", 15, 0x00, SI_LIT_FFFFFFFF)
  // ( -- 0xFFFFFFFF )
  push TOS
  li TOS, 0xFFFF
  liu TOS, 0xFFFF
  NEXT

DEFCODE("SI_EQU_ZBRANCH", 14, 0x00, SI_EQU_ZBRANCH)
  // ( a b -- )
  pop W
  cmp W, TOS
  // if a == b, flag = TRUE => ZBRANCH should not trigger
  be __SI_EQU_ZBRANCH_fail
  lw W, FIP
  add FIP, W
  j __SI_EQU_ZBRANCH_next
__SI_EQU_ZBRANCH_fail:
  add FIP, CELL
__SI_EQU_ZBRANCH_next:
  pop TOS
  NEXT

#endif
