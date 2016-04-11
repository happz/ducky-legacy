\ https://rosettacode.org/wiki/Sieve_of_Eratosthenes#Forth

: PRIME? ( n -- ? ) HERE + C@ 0= ;
: COMPOSITE! ( n -- ) HERE + 1 SWAP C! ;

: SIEVE ( n -- )
  HERE OVER ERASE
  2
  BEGIN
    2DUP DUP * >
  WHILE
    DUP PRIME? IF
      2DUP DUP * DO
        I COMPOSITE!
      DUP +LOOP
    THEN
    1+
  REPEAT
  DROP
  ." Primes: " 2 DO I PRIME? IF I . THEN LOOP CR ;

DECIMAL 100 SIEVE
