VMDEBUGOFF

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


: CONSTANT WORD HEADER, DOCOL , ['] LIT , , ['] EXIT , ;
: VARIABLE WORD HEADER, DODOES , 0 ,  1 CELLS ALLOT ;
: CREATE   WORD HEADER, DODOES , 0 ,  ;
: DOES> R> LATEST @ >DFA ! ;
: VALUE WORD HEADER, DOCOL , ['] LIT , , ['] EXIT , ;


: REPEAT IMMEDIATE ['] BRANCH , SWAP HERE - , DUP HERE SWAP - SWAP ! ;
: AGAIN IMMEDIATE ['] BRANCH , HERE - , ;
: UNLESS IMMEDIATE ['] NOT , [COMPILE] IF ;

CREATE LEAVE-SP 32 CELLS ALLOT
LEAVE-SP LEAVE-SP !

: LEAVE IMMEDIATE ['] UNLOOP , ['] BRANCH , LEAVE-SP @ LEAVE-SP - 31 CELLS > IF ABORT THEN 1 CELLS LEAVE-SP +! HERE LEAVE-SP @ ! 0 , ;
: RESOLVE-DO IF DUP HERE - , DUP 2 CELLS - HERE OVER - SWAP ! ELSE DUP HERE - , THEN ;
: RESOLVE-LEAVES BEGIN LEAVE-SP @ @ OVER > LEAVE-SP @ LEAVE-SP > AND WHILE HERE LEAVE-SP @ @ - LEAVE-SP @ @ ! 1 CELLS NEGATE LEAVE-SP +! REPEAT DROP ;
: DO IMMEDIATE ['] (DO) , HERE 0 ;
: ?DO IMMEDIATE ['] 2DUP , ['] <> , ['] 0BRANCH , 0 , ['] (DO) , HERE 1 ;
: LOOP IMMEDIATE ['] (LOOP) , RESOLVE-DO RESOLVE-LEAVES ;


\ PRINTING NUMBERS ----------------------------------------------------------------------

\ This is the underlying recursive definition of U.
: U.		( u -- )
	BASE @ /MOD	( width rem quot )
	?DUP IF			( if quotient <> 0 then )
		RECURSE		( print the quotient )
	THEN

	( print the remainder )
	DUP 10 < IF
		'0'		( decimal digits 0..9 )
	ELSE
		10 -		( hex and beyond digits A..Z )
		'A'
	THEN
	+
	EMIT
;

\ Prints the contents of the stack.
: .S		( -- )
	DSP@		( get current stack pointer )
	BEGIN
		DUP S0 @ <
	WHILE
		DUP @ U.	( print the stack element )
		SPACE
		2+		( move up )
	REPEAT
	DROP
;

\ Returns the width (in characters) of an unsigned number in the current base
\ : UWIDTH BASE @ /	?DUP IF RECURSE 1+ ELSE 1 THEN ;

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

: TO IMMEDIATE	( n -- )
	WORD		( get the name of the value )
	FIND		( look it up in the dictionary )
	>DFA		( get a pointer to the first data field (the 'LIT') )
	2+		( increment to point at the value )
	STATE @ IF	( compiling? )
		['] LIT	,	( compile LIT )
		,		( compile the address of the value )
		['] !	,	( compile ! )
	ELSE		( immediate mode )
		!		( update it straightaway )
	THEN
;

( x +TO VAL adds x to VAL )
: +TO IMMEDIATE
	WORD		( get the name of the value )
	FIND		( look it up in the dictionary )
	>DFA		( get a pointer to the first data field (the 'LIT') )
	2+		( increment to point at the value )
	STATE @ IF	( compiling? )
		['] LIT	,	( compile LIT )
		,		( compile the address of the value )
		['] +! ,		( compile +! )
	ELSE		( immediate mode )
		+!		( update it straightaway )
	THEN
;

\ - PRINTING THE DICTIONARY ---------------------------------------------------------------------

\ ID. takes an address of a dictionary entry and prints the word's name.
: ID.
  3 +   ( skip over the link pointer and flags byte )
	DUP C@		( get the flags/length byte )

	BEGIN
		DUP 0>		( length > 0? )
	WHILE
		SWAP 1+		( addr len -- len addr+1 )
		DUP C@		( len addr -- len addr char | get the next character)
		EMIT		( len addr char -- len addr | and print it)
		SWAP 1-		( len addr -- addr len-1    | subtract one from length )
	REPEAT
	2DROP		( len addr -- )
;

\ WORDS prints all the words defined in the dictionary, starting with the word defined most recently.
\ However it doesn't print hidden words.
: WORDS
	LATEST @	( start at LATEST dictionary entry )
	BEGIN
		?DUP		( while link pointer is not null )
	WHILE
		DUP ?HIDDEN NOT IF	( ignore hidden words )
			DUP ID.		( but if not hidden, print the word )
			SPACE
		THEN
		@		( dereference the link pointer - go to previous word )
	REPEAT
	CR
;

\ : FORGET WORD FIND DUP @ LATEST !	HERE ! ;

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
			?DUP		( while linelen > 0)
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

\ - CASE ---------------------------------------------------------------------

: CASE IMMEDIATE
	0		( push 0 to mark the bottom of the stack )
;

: OF IMMEDIATE
	['] OVER , ( compile OVER )
	['] = ,		( compile = )
	[COMPILE] IF	( compile IF )
	['] DROP , ( compile DROP )
;

: ENDOF IMMEDIATE
	[COMPILE] ELSE	( ENDOF is the same as ELSE )
;

: ENDCASE IMMEDIATE
	['] DROP , ( compile DROP )

	( keep compiling THEN until we get to our zero marker )
	BEGIN
		?DUP
	WHILE
		[COMPILE] THEN
	REPEAT
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
  S" TEST-MODE" FIND NOT IF
    ." DuckyFORTH VERSION " VERSION . CR
    UNUSED . ." CELLS REMAINING" CR
    ." OK " CR
  THEN
;

WELCOME
HIDE WELCOME

