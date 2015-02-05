;
; Interrupts
;
.def INT_HALT:    0
.def INT_BLOCKIO: 1
.def INT_VMDEBUG: 2
.def INT_CONIO:   3


;
; IO ports
;

; Console IO
.def PORT_CONIO_STDIN:  0x100
.def PORT_CONIO_STDOUT: 0x100
.def PORT_CONIO_STDERR: 0x101

; Block IO
.def PORT_BLOCKIO_CMD:  0x200
.def PORT_BLOCKIO_DATA: 0x202

