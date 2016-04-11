\ https://rosettacode.org/wiki/Sum_digits_of_an_integer#Forh

: SUM-INT 0 BEGIN OVER WHILE SWAP BASE @ /MOD SWAP ROT + REPEAT NIP ;

T{ 2 BASE ! 11110 SUM-INT -> #4  }T
T{ DECIMAL  12345 SUM-INT -> #15 }T
T{ HEX      F0E   SUM-INT -> #29 }T
