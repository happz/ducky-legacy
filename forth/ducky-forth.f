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


\ PRINTING NUMBERS ----------------------------------------------------------------------

\ Prints an unsigned number, padded to a certain width
: U.R		( u width -- )
	SWAP		( width u )
	DUP		( width u u )
	UWIDTH		( width u uwidth )
	ROT		( u uwidth width )
	SWAP -		( u width-uwidth )
	( At this point if the requested width is narrower, we'll have a negative number on the stack.
	  Otherwise the number on the stack is the number of spaces to print.  But SPACES won't print
	  a negative number of spaces anyway, so it's now safe to call SPACES ... )
	SPACES
	( ... and then call the underlying implementation of U. )
	U.
;

\ Prints a signed number, padded to a certain width.  We can't just print the sign
\ and call U.R because we want the sign to be next to the number ('-123' instead of '-  123').
: .R		( n width -- )
	SWAP		( width n )
	DUP 0< IF
		NEGATE		( width u )
		1		( save a flag to remember that it was negative | width n 1 )
		SWAP		( width 1 u )
		ROT		( 1 u width )
		1-		( 1 u width-1 )
	ELSE
		0		( width u 0 )
		SWAP		( width 0 u )
		ROT		( 0 u width )
	THEN
	SWAP		( flag width u )
	DUP		( flag width u u )
	UWIDTH		( flag width u uwidth )
	ROT		( flag u uwidth width )
  SWAP -    ( flag u width-uwidth )

  SPACES    ( flag u )
  SWAP    ( u flag )

	IF			( was it negative? print the - character )
		'-' EMIT
	THEN

	U.
;

\ Finally we can define word . in terms of .R, with a trailing space.
: . 0 .R SPACE ;

\ The real U., note the trailing space.
: U. U. SPACE ;

\ ? fetches the integer at an address and prints it.
: ? ( addr -- ) @ . ;


\ - STRINGS ---------------------------------------------------------------------

\ ." is the print string operator in FORTH.  Example: ." Something to print"
: ." IMMEDIATE		( -- )
	STATE @ IF	( compiling? )
		[COMPILE] S"	( read the string, and compile LITSTRING, etc. )
		['] TELL , ( compile the final TELL )
	ELSE
		( In immediate mode, just read characters and print them until we get
		  to the ending double quote. )
		BEGIN
			KEY
			DUP '"' = IF
				DROP	( drop the double quote character )
				EXIT	( return from this function )
			THEN
			EMIT
		AGAIN
	THEN
;

\ - PRINTING THE DICTIONARY ---------------------------------------------------------------------

\ DUMP is used to dump out the contents of memory, in the 'traditional' hexdump format.
: DUMP		( addr len -- )
	BASE @ -ROT		( save the current BASE at the bottom of the stack )
	HEX			( and switch to hexadecimal mode )

	BEGIN
		?DUP		( while len > 0 )
	WHILE
		OVER 8 U.R	( print the address )
		SPACE

		( print up to 16 words on this line )
		2DUP		( addr len addr len )
		1- 15 AND 1+	( addr len addr linelen )
		BEGIN
			?DUP		( while linelen > 0 )
		WHILE
			SWAP		( addr len linelen addr )
			DUP C@		( addr len linelen addr byte )
			2 .R SPACE	( print the byte )
			1+ SWAP 1-	( addr len linelen addr -- addr len addr+1 linelen-1 )
		REPEAT
		DROP		( addr len )

		( print the ASCII equivalents )
		2DUP 1- 15 AND 1+ ( addr len addr linelen )
		BEGIN
			?DUP		( while linelen > 0 )
		WHILE
			SWAP		( addr len linelen addr )
			DUP C@		( addr len linelen addr byte )
			DUP 32 128 WITHIN IF	( 32 <= c < 128? )
				EMIT
			ELSE
				DROP '.' EMIT
			THEN
			1+ SWAP 1-	( addr len linelen addr -- addr len addr+1 linelen-1 )
		REPEAT
		DROP		( addr len )
		CR

		DUP 1- 15 AND 1+ ( addr len linelen )
		TUCK		( addr linelen len linelen )
		-		( addr linelen len-linelen )
		>R + R>		( addr+linelen len-linelen )
	REPEAT

	DROP			( restore stack )
	BASE !			( restore saved BASE )
;

\ - DECOMPILER ---------------------------------------------------------------------

: CFA>
	LATEST @	( start at LATEST dictionary entry )
	BEGIN
		?DUP		( while link pointer is not null )
	WHILE
		2DUP SWAP	( cfa curr curr cfa )
		< IF		( current dictionary entry < cfa? )
			NIP		( leave curr dictionary entry on the stack )
			EXIT
		THEN
		@		( follow link pointer back )
	REPEAT
	DROP		( restore stack )
	0		( sorry, nothing found )
;


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
