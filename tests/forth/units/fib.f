DECIMAL

: FIB ( n1 -- n2 )
  DUP 2 < IF
    DROP 1
  ELSE
    DUP 1- RECURSE
    SWAP 2 - RECURSE
    +
  THEN
;

T{ 22 FIB -> 28657 }T
