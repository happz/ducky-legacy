ducky
=====

Ducky is a simple virtual CPU/machine simulator, with modular design and interesting features.

.. image:: https://img.shields.io/pypi/v/ducky.svg
  :target: https://pypi.python.org/pypi/ducky/

.. image:: https://readthedocs.org/projects/ducky/badge/?version=latest
  :target: http://ducky.readthedocs.org/en/latest/

.. image:: https://circleci.com/gh/happz/ducky.svg?style=svg
  :target: https://circleci.com/gh/happz/ducky

.. image:: http://www.quantifiedcode.com/api/v1/project/e7859c764ad2426fae178204016ba5b4/badge.svg
  :target: http://www.quantifiedcode.com/app/project/e7859c764ad2426fae178204016ba5b4

.. image:: https://api.codacy.com/project/badge/23fdf5e716e64cddadb42e9ae672dbbc
  :target: https://www.codacy.com/app/happz/ducky

.. image:: https://codeclimate.com/github/happz/ducky/badges/issue_count.svg
  :target: https://codeclimate.com/github/happz/ducky
  :alt: Issue Count

.. image:: https://coveralls.io/repos/happz/ducky/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/happz/ducky?branch=master

.. image:: https://img.shields.io/docker/pulls/happz/ducky-forth-python2.7.svg
  :target: https://hub.docker.com/r/happz/ducky-forth-python2.7/

Ducky was created for learning purposes, no bigger ambitions. The goal was to experiment with
CPU and virtual machine simulation, different instruction sets, and later working FORTH kernel
become one of the main goals.


Features
--------

Ducky - as in "Ducky, the CPU" - is a 32-bit RISC CPU. Ducky, "the VM", is a simulator of Ducky CPU, adding few other modules to create the whole virtual machine, with CPUs, peripherals, storages and other components.


RISC instruction set
^^^^^^^^^^^^^^^^^^^^

Instruction set was inspired by RISC CPUs, and sticks to LOAD/STORE aproach, with fixed-width instructions.


Memory model
^^^^^^^^^^^^

Flat, paged, with linear addressing. Main memory consists of memory pages, each page supports simple access control - simple MMU is implemented.


Modular architecture
^^^^^^^^^^^^^^^^^^^^

Virtual machine consists of several modules of different classes, and only few of them are necessary (e.g. CPU). Various peripherals are available, and it's extremely easy to develop your own and plug them in.


SMP support
^^^^^^^^^^^

Multiple CPUs with multiple cores per each CPU, with shared memory. Each core can be restricted to its own segment of memory.


Persistent storage
^^^^^^^^^^^^^^^^^^

Modular persistent storages are available, and accessible by block IO operations, or by mmap-ing storages directly into memory.


Bytecode files
^^^^^^^^^^^^^^

Compiled programs are stored in bytecode files that are inspired by ELF executable format. These files consist of common sections (``.text``, ``.data``, ...), symbols, and their content. Assembler (``ducky-as``) translates assembler sources into object files, and these are then processed by a linker (``ducky-ld``) into the final executable. Both object and executable files use the same format and bytecode for instructions and data.


Snapshots
^^^^^^^^^

Virtual machine can be suspended, saved, and later restored. This is also useful for debugging purposes, every bit of memory and CPU registers can be investigated.


Debugging support
^^^^^^^^^^^^^^^^^

Basic support is included - break points, watch points, stack traces, stepping, snapshots, ...


Tools
^^^^^

- ``as`` for translating assembler sources to bytecode files
- ``ld`` for linking bytecode files into the final executable
- ``objdump`` for inspection of bytecode files
- ``coredump`` for inspection of snapshots
- ``vm`` for running virtual machine itself
- ``img`` for converting binaries to images
- and ``cc``, an experimental C compiler


Planned features
^^^^^^^^^^^^^^^^

- ``FORTH`` kernel - basic functionality but at least ANS compliant
- network support - it would be awesome to have a network stack available for running programs
- functioning C compiler, with simple C library
- and few others...


Need help?
----------

The whole development is tracked on a GitHub `page <http://github.com/happz/ducky/>`_, including source codes and issue tracker.
