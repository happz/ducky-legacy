Tools
=====


Ducky comes with basic toolchain necessary for development of complex programs. One piece missing is the C cross-compiler with simple C library but this issue will be resolved very soon :)


as
--

Assembler. Translates assembler files (``.asm``) to `binaries` - files containing bytecode, symbols information, etc. that can by executed by VM.


coredump
--------

Prints information stored in a saved VM snapshot.


objdump
-------

Prints information about binary file.


profile
-------

Prints information stored in profiling data, created by VM. Used for profiling running binaries.

