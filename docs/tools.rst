Tools
=====


Ducky comes with basic toolchain necessary for development of complex programs. One piece missing is the C cross-compiler with simple C library but this issue will be resolved very soon :)


as
--

Assembler. Translates *assembler files* (``.asm``) to *object files* (``.o``) -  files containing bytecode, symbols information, etc.


ld
--

Linker. Takes (one or multiple) *object files* and merges them into one, *binary*, which can be executed by VM.


coredump
--------

Prints information stored in a saved VM snapshot.


objdump
-------

Prints information about object and binary files.


profile
-------

Prints information stored in profiling data, created by VM. Used for profiling running binaries.


vm
--

Stand-alone virtual machine - takes binary, configuration files, and other resources, and executes binaries.
