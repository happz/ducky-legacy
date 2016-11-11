DEFCSTUB("<#", 2, 0x00, LESSNUMBERSIGN)
  // ( -- )

DEFCODE(".", 1, 0x00, DOT)
  // ( n -- )
  mov r0, TOS
  pop TOS
  call print_i32
  call do_SPACE
  NEXT


DEFCODE("?", 1, 0x00, QUESTION)
  // ( a-addr -- )
  lw r0, TOS
  pop TOS
  call print_i32
  call do_SPACE
  NEXT


DEFCODE("U.", 2, 0x00, UDOT)
  // ( u -- )
  mov r0, TOS
  pop TOS
  call print_u32
  call do_SPACE
  NEXT
