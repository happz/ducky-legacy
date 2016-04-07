\ A minimal FORTH kernel for Ducky virtual machine
\
\ This was written as an example and for educating myself, no higher ambitions intended.
\
\ Heavily based on absolutely amazing FORTH tutorial by
\ Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
\
\ This file contains words that I find useful to be implemented using FORTH words, in text.
\ Later there should be more of right-now hardcoded words but this separation helps a lot
\ to speed up loading, development and testing.
\


CREATE LEAVE-SP 32 CELLS ALLOT
LEAVE-SP LEAVE-SP !

: LEAVE IMMEDIATE ['] UNLOOP , ['] BRANCH , LEAVE-SP @ LEAVE-SP - 31 CELLS > IF ABORT THEN 1 CELLS LEAVE-SP +! HERE LEAVE-SP @ ! 0 , ;
: RESOLVE-DO IF DUP HERE - , DUP 2 CELLS - HERE OVER - SWAP ! ELSE DUP HERE - , THEN ;
: RESOLVE-LEAVES BEGIN LEAVE-SP @ @ OVER > LEAVE-SP @ LEAVE-SP > AND WHILE HERE LEAVE-SP @ @ - LEAVE-SP @ @ ! 1 CELLS NEGATE LEAVE-SP +! REPEAT DROP ;
: DO IMMEDIATE ['] (DO) , HERE 0 ;
: ?DO IMMEDIATE ['] 2DUP , ['] <> , ['] 0BRANCH , 0 , ['] (DO) , HERE 1 ;
: LOOP IMMEDIATE ['] (LOOP) , RESOLVE-DO RESOLVE-LEAVES ;
: +LOOP IMMEDIATE ['] (+LOOP) , RESOLVE-DO RESOLVE-LEAVES ;


\ - WELCOME MESSAGE ---------------------------------------------------------------------

: WELCOME
  C" TEST-MODE" FIND SWAP DROP NOT IF
    ." DuckyFORTH VERSION " VERSION . CR
    ." Build " BUILD-STAMP TYPE CR
    UNUSED . ." CELLS REMAINING" CR
    TRUE SHOW-PROMPT !
  THEN
;

WELCOME HIDE WELCOME
