Introduction
============

Ducky is a simple virtual 16bit CPU/machine simulator, with modular design and many interesting features.


About Ducky
-----------

Ducky was created for learning purposes, no bigger ambitions. The goal was to experiment with
CPU and virtual machine simulation, different instruction sets, and later working FORTH kernel
become one of the main goals.


Features
--------

Modular architecture
^^^^^^^^^^^^^^^^^^^^

Virtual machine consists of several modules of different classes, and only few ow them are necessary (e.g. CPU). Various peripherals are available, and it's extremely easy to develop your own and plug them in.


SMP support
^^^^^^^^^^^

Multiple CPUs with multiple cores per each CPU, with shared memory. Each core can be restricted to its own segment of memory.


RISC instruction set
^^^^^^^^^^^^^^^^^^^^

Instruction set was inspired by RISC CPUs and sticks to LOAD/STORE aproach, with fixed-width instructions.


Memory model
^^^^^^^^^^^^

Flat, paged, segmented, with linear addressing. Main memory consists of memory pages, and is divided into segments, defined by the fact that internal address bus is only 16 bits wide. The whole memory can be much larger, and only CPU cores running in privileged mode can switch their segments, and therefore access any byte in memory. Each memory page supports simple access control.


Persistent storage
^^^^^^^^^^^^^^^^^^

Modular persistent storages are available, and accessible by block IO operations, or by mmap-ing storages directly into memory.


Bytecode files
^^^^^^^^^^^^^^

Compiled programs are stored in bytecode files that are inspired by ELF executable format. These files consist of common sections (``.text``, ``.data``, ...), symbols, and their content.


Snapshots
^^^^^^^^^

Virtual machine can be suspended, saved, and later restored. This is also useful for debugging purposes, every bit of memory and CPU registers can be investigated.


Debugging support
^^^^^^^^^^^^^^^^^

Basic support is included - break points, watch points, stack traces, stepping, snapshots, ...


Tools
^^^^^

- ``as`` for translating assembler sources to bytecode files
- ``objdump`` for inspection of bytecode files
- ``coredump`` for inspection of snapshots
- ``vm`` for running virtual machine itself
- and ``cc``, an experimental C compiler


Planned features
^^^^^^^^^^^^^^^^

- ``FORTH`` kernel - basic functionality but at least ANS compliant
- network support - it would be awesome to have a network stack available for running programs
- more freedom for bytecode - relocation support, dynamic load/unload of bytecode in runtime
- functional C compiler, with simple C library
- and few others...

Need help?
----------

The whole development is tracked on a GitHub `page <http://github.com/happz/ducky/>`_, including
source codes and issue tracker.
