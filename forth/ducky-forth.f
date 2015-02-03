VMDEBUGOFF

\ A minimal FORTH kernel for Ducky virtual machine
\
\ This was written as an example and for educating myself, no higher ambitions intended.
\
\ Heavily based on absolutely amazing FORTH tutorial by
\ Richard W.M. Jones <rich@annexia.org> http://annexia.org/forth
\

\ - Some utilities -----------------------------------------------------------------------

\ This is fake - exceptions are not implemented yet
: ABORT
  \ ( -- )
  BYE
;


\ - Character constants -------------------------------------------------------------------

: '\n' 10 ;

: BL   32 ;


\ - Helpers -------------------------------------------------------------------------------

\ Prints a carriage return
: CR    '\n' EMIT ;

\ Prints a space
: SPACE BL   EMIT ;

\ NEGATE leaves the negative of a number on the stack.
: NEGATE 0 SWAP - ;

\ Negate condition
: NOT   0= ;

\ LITERAL takes whatever is on the stack and compiles LIT <foo>
: LITERAL IMMEDIATE
	' LIT ,
	,
	;

\ Literals calculated at compile time
: ':' [ CHAR : ] LITERAL ;

: ';' [ CHAR ; ] LITERAL ;
: '(' [ CHAR ( ] LITERAL ;
: ')' [ CHAR ) ] LITERAL ;
: '"' [ CHAR " ] LITERAL ;
: 'A' [ CHAR A ] LITERAL ;
: '0' [ CHAR 0 ] LITERAL ;
: '-' [ CHAR - ] LITERAL ;
: '.' [ CHAR . ] LITERAL ;

\ Multiply TOS by 2 (cell size)
: CELLS 2 * ;

\ Alloc N bytes in userspace memory by putting old value of HERE on stack and increasing its value
: ALLOT   \ n -- addr
  HERE @ SWAP \ here n
  HERE +!     \ adds n to HERE
;

\ - CONSTANTS AND VARIABLES ---------------------------------------------------------------------
: CONSTANT
	CREATE
	DOCOL ,
	' LIT ,
	,
	' EXIT ,
;

: ARRAY
  \ ( n_items -- )
  CELLS ALLOT
  CREATE
  DOCOL ,
  ' LIT ,
  ,
  ' EXIT ,
;

: VARIABLE
	1 CELLS ALLOT
	CREATE
	DOCOL ,
	' LIT ,
	,
	' EXIT ,
;

: VALUE
	CREATE
	DOCOL ,
	' LIT ,
	,
	' EXIT ,
;

\ While compiling, '[COMPILE] word' compiles 'word' if it would otherwise be IMMEDIATE.
: [COMPILE] IMMEDIATE
	WORD		\ get the next word
	FIND		\ find it in the dictionary
	>CFA		\ get its codeword
	,		\ and compile that
;

\ RECURSE makes a recursive call to the current word that is being compiled.
: RECURSE IMMEDIATE
	LATEST @	\ LATEST points to the word being compiled at the moment
	>CFA		\ get the codeword
	,		\ compile it
;

\	- Control structures ----------------------------------------------------------------------

\ IF is an IMMEDIATE word which compiles 0BRANCH followed by a dummy offset, and places
\ the address of the 0BRANCH on the stack.  Later when we see THEN, we pop that address
\ off the stack, calculate the offset, and back-fill the offset.
: IF IMMEDIATE
	' 0BRANCH ,	\ compile 0BRANCH
	HERE @		\ save location of the offset on the stack
	0 ,		\ compile a dummy offset
;

: THEN IMMEDIATE
	DUP
	HERE @ SWAP -	\ calculate the offset from the address saved on the stack
	SWAP !		\ store the offset in the back-filled location
;

: ELSE IMMEDIATE
	' BRANCH ,	\ definite branch to just over the false-part
	HERE @		\ save location of the offset on the stack
	0 ,		\ compile a dummy offset
	SWAP		\ now back-fill the original (IF) offset
	DUP		\ same as for THEN word above
	HERE @ SWAP -
	SWAP !
;

\ BEGIN loop-part condition UNTIL
\	-- compiles to: --> loop-part condition 0BRANCH OFFSET
\	where OFFSET points back to the loop-part
\ This is like do { loop-part } while (condition) in the C language
: BEGIN IMMEDIATE
	HERE @		\ save location on the stack
;

: UNTIL IMMEDIATE
	' 0BRANCH ,	\ compile 0BRANCH
	HERE @ -	\ calculate the offset from the address saved on the stack
	,		\ compile the offset here
;

\ BEGIN loop-part AGAIN
\	-- compiles to: --> loop-part BRANCH OFFSET
\	where OFFSET points back to the loop-part
\ In other words, an infinite loop which can only be returned from with EXIT
: AGAIN IMMEDIATE
	' BRANCH ,	\ compile BRANCH
	HERE @ -	\ calculate the offset back
	,		\ compile the offset here
;

\ BEGIN condition WHILE loop-part REPEAT
\	-- compiles to: --> condition 0BRANCH OFFSET2 loop-part BRANCH OFFSET
\	where OFFSET points back to condition (the beginning) and OFFSET2 points to after the whole piece of code
\ So this is like a while (condition) { loop-part } loop in the C language
: WHILE IMMEDIATE
	' 0BRANCH ,	\ compile 0BRANCH
	HERE @		\ save location of the offset2 on the stack
	0 ,		\ compile a dummy offset2
;

: REPEAT IMMEDIATE
	' BRANCH ,	\ compile BRANCH
	SWAP		\ get the original offset (from BEGIN)
	HERE @ - ,	\ and compile it after BRANCH
	DUP
	HERE @ SWAP -	\ calculate the offset2
	SWAP !		\ and back-fill it in the original location
;

\ UNLESS is the same as IF but the test is reversed.
: UNLESS IMMEDIATE
	' NOT ,		\ compile NOT (to reverse the test)
	[COMPILE] IF	\ continue by calling the normal IF
;

32 CELLS ARRAY LEAVE-SP
LEAVE-SP LEAVE-SP !

: LEAVE
  ' UNLOOP ,
  ' BRANCH ,
  LEAVE-SP @ LEAVE-SP - 31 CELLS >
  IF ABORT THEN
  1 CELLS LEAVE-SP +!
  HERE @ LEAVE-SP @ !
  0 ,
; IMMEDIATE

: RESOLVE-LEAVES \ ( here - )
  BEGIN
    LEAVE-SP @ @ OVER >
    LEAVE-SP @ LEAVE-SP >  AND
  WHILE
    HERE @ LEAVE-SP @ @ - LEAVE-SP @ @ !
    1 CELLS NEGATE LEAVE-SP +!
  REPEAT
  DROP
;

: DO
  ' (DO) ,
  HERE @ 0
; IMMEDIATE

: ?DO
  ' 2DUP ,
  ' <> ,
  ' 0BRANCH ,
  0 ,
  ' (DO) ,
  HERE @ 1
; IMMEDIATE

: RESOLVE-DO
  \ ( here 0|1 -- here )
  IF \ ( ?DO )
    DUP HERE @ - ,
    DUP 2 CELLS - HERE @ OVER - SWAP !
  ELSE \ ( DO )
    DUP HERE @ - ,
  THEN
;

: LOOP
  \ ( here 0|1 -- )
  ' (LOOP) ,
  RESOLVE-DO
  RESOLVE-LEAVES
; IMMEDIATE

\ : +LOOP
\   \ ( here 0|1 --)
\   ' (+LOOP) ,
\   RESOLVE-DO
\ ; IMMEDIATE


\	COMMENTS ----------------------------------------------------------------------
\
\ FORTH allows ( ... ) as comments within function definitions.  This works by having an IMMEDIATE
\ word called ( which just drops input characters until it hits the corresponding ).
: ( IMMEDIATE
	1		\ allowed nested parens by keeping track of depth
	BEGIN
		KEY		\ read next character
		DUP '(' = IF	\ open paren?
			DROP		\ drop the open paren
			1+		\ depth increases
		ELSE
			')' = IF	\ close paren?
				1-		\ depth decreases
			THEN
		THEN
	DUP 0= UNTIL		\ continue until we reach matching close paren, depth 0
	DROP		\ drop the depth counter
;

(
	From now on we can use ( ... ) for comments.

	STACK NOTATION ----------------------------------------------------------------------

	In FORTH style we can also use ( ... -- ... ) to show the effects that a word has on the
	parameter stack.  For example:

	( n -- )	means that the word consumes an integer (n) from the parameter stack.
	( b a -- c )	means that the word uses two integers (a and b, where a is at the top of stack)
				and returns a single integer (c).
	( -- )		means the word has no effect on the stack
)

: NIP ( x y -- y ) SWAP DROP ;

: TUCK ( x y -- y x y ) SWAP OVER ;

: PICK ( x_n ... x_1 x_0 n -- x_u ... x_1 x_0 x_n )
	1+		 ( add one because of 'n' on the stack )
  CELLS  ( multiply by the word size )
	DSP@ + ( add to the stack pointer )
	@      ( and fetch )
;

( With the looping constructs, we can now write SPACES, which writes n spaces to stdout. )
: SPACES	( n -- )
	BEGIN
		DUP 0>		( while n > 0 )
	WHILE
		SPACE		( print a space )
		1-		( until we count down to 0 )
	REPEAT
	DROP
;

( Standard words for manipulating BASE. )
: DECIMAL ( -- ) 10 BASE ! ;
: HEX ( -- ) 16 BASE ! ;

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
: UWIDTH	( u -- width )
	BASE @ /	( rem quot )
	?DUP IF		( if quotient <> 0 then )
		RECURSE 1+	( return 1+recursive call )
	ELSE
		1		( return 1 )
	THEN
;

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
	SWAP -		( flag u width-uwidth )

	SPACES		( flag u )
	SWAP		( u flag )

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

\ c a b WITHIN returns true if a <= c and c < b
\  or define without ifs: OVER - >R - R>  U<
: WITHIN
	-ROT		( b c a )
	OVER		( b c a c )
	<= IF
		> IF		( b c -- )
			TRUE
		ELSE
			FALSE
		THEN
	ELSE
		2DROP		( b c -- )
		FALSE
	THEN
;

\ DEPTH returns the depth of the stack.
: DEPTH		( -- n )
	S0 @ DSP@ -
	2-			( adjust because S0 was on the stack when we pushed DSP )
;

\	ALIGNED takes an address and rounds it up (aligns it) to the next cell boundary.
: ALIGNED	( addr -- addr )
  1 + 1 INVERT AND ( (addr + 1) & ~1 )
;

\ ALIGN aligns the HERE pointer, so the next word appended will be aligned properly.
: ALIGN HERE @ ALIGNED HERE ! ;

\ - STRINGS ---------------------------------------------------------------------
\ C, appends a byte to the current compiled word.
: C,
	HERE @ C!	( store the character in the compiled image )
	1 HERE +!	( increment HERE pointer by 1 byte )
;

: S" IMMEDIATE		( -- addr len )
	STATE @ IF	( compiling? )
		' LITSTRING ,	( compile LITSTRING )
		HERE @		( save the address of the length word on the stack )
		0 ,		( dummy length - we don't know what it is yet )
		BEGIN
			KEY 		( get next character of the string )
			DUP '"' <>
		WHILE
			C,		( copy character )
		REPEAT
		DROP		( drop the double quote character at the end )
		DUP		( get the saved address of the length word )
		HERE @ SWAP -	( calculate the length )
		2-		( subtract 2 (because we measured from the start of the length word) )
		SWAP !		( and back-fill the length location )
		ALIGN		( round up to next multiple of 2 bytes for the remaining code )
	ELSE		( immediate mode )
		HERE @		( get the start address of the temporary space )
		BEGIN
			KEY
			DUP '"' <>
		WHILE
			OVER C!		( save next character )
			1+		( increment address )
		REPEAT
		DROP		( drop the final " character )
		HERE @ -	( calculate the length )
		HERE @		( push the start address )
		SWAP 		( addr len )
	THEN
;

\ ." is the print string operator in FORTH.  Example: ." Something to print"
: ." IMMEDIATE		( -- )
	STATE @ IF	( compiling? )
		[COMPILE] S"	( read the string, and compile LITSTRING, etc. )
		' TELL ,	( compile the final TELL )
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
		' LIT ,		( compile LIT )
		,		( compile the address of the value )
		' ! ,		( compile ! )
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
		' LIT ,		( compile LIT )
		,		( compile the address of the value )
		' +! ,		( compile +! )
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

\ 'WORD word FIND ?HIDDEN' returns true if 'word' is flagged as hidden.
: ?HIDDEN
  2+    ( skip over the link pointer )
	C@		( get the flags byte )
	F_HIDDEN AND	( mask the F_HIDDEN flag and return it (as a truth value) )
;

\ 'WORD word FIND ?IMMEDIATE' returns true if 'word' is flagged as immediate.
: ?IMMEDIATE
  2+    ( skip over the link pointer )
	C@		( get the flags byte )
	F_IMMED AND	( mask the F_IMMED flag and return it (as a truth value) )
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

\ Deletes the definition of 'word' from the dictionary and everything defined
\ after it, including any variables and other memory allocated after.
: FORGET
	WORD FIND	( find the word, gets the dictionary entry address )
	DUP @ LATEST !	( set LATEST to point to the previous word )
	HERE !		( and store HERE with the dictionary address )
;

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
	' OVER ,	( compile OVER )
	' = ,		( compile = )
	[COMPILE] IF	( compile IF )
	' DROP ,  	( compile DROP )
;

: ENDOF IMMEDIATE
	[COMPILE] ELSE	( ENDOF is the same as ELSE )
;

: ENDCASE IMMEDIATE
	' DROP ,	( compile DROP )

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
	." DuckyFORTH VERSION " VERSION . CR
		." OK "
;

