Getting started
===============


Installing
----------

The easy way is to use package::

  pip install ducky


Or, you can install Ducky by checking out the sources::

  git clone https://github.com/happz/ducky.git
  cd ducky
  python setup.py


After this, you should have the ``ducky`` module on your path::

  >>> import ducky
  >>> ducky.__version__
  '3.0'


Prerequisites
-------------

Ducky runs with both Python 2 *and* 3 - supported versions are 2.7, 3.3, 3.4
and 3.5. There are few other dependencies, installation process (or ``setup.py``)
should take care of them autmatically. PyPy is also supported, though only its
implementation of Python2.


"Hello, world!" tutorial
------------------------

Let's try out the "Hello, world!" example. It's a simple program that just prints
out the well-known message.


Source code
^^^^^^^^^^^

Source is located in ``examples/hello-world`` directory. If you check it out, it's
a plain and simple assembler:

.. code-block:: gas

  #include <arch/tty.hs>

  .data

  .type stack, space, 64
  .type message, string, "Hello, world!"


  .text

  main:
    la sp, stack
    add sp, 64

    la r0, message
    call writesn
    hlt 0x00

  writesn:
    // > r0: string address
    // ...
    //   r0: port
    //   r1: current byte
    //   r2: string ptr
    push r1
    push r2
    mov r2, r0
    li r0, TTY_MMIO_ADDRESS
    add r0, TTY_MMIO_DATA

  .__writesn_loop:
    lb r1, r2
    bz .__writesn_write_nl
    stb r0, r1
    inc r2
    j .__writesn_loop

  .__writesn_write_nl:
    // \n
    li r1, 0x0000000A
    stb r0, r1
    // \r
    li r1, 0x0000000D
    stb r0, r1
    li r0, 0x00000000
    pop r2
    pop r1
    ret


It's a little bit more structured that necessary, just for educational purposes.


Binary
^^^^^^

To run this code, we have to create a :term:`binary` of it. Of course, there
are tools for this very common goal:

.. code-block:: none

  ducky-as -i examples/hello-world/hello-world.s -o examples/hello-world/hello-world.o

This command will translate source code to an :term:`object file` which contains
instructions and other necessary resources for :term:`machine` to run it. You
can inspect the object file using ``objdump`` tool:

.. code-block:: none

  ducky-objdump -i examples/hello-world/hello-world.o -a

This should produce output similar to this one:

.. code-block:: none

  [INFO] Input file: examples/hello-world/hello-world.o
  [INFO] 
  [INFO] === File header ===
  [INFO]   Magic:    0xDEAD
  [INFO]   Version:  1
  [INFO]   Sections: 4
  [INFO] 
  [INFO] === Sections ===
  [INFO] 
  [INFO]   Index  Name      Type     Flags        Base        Items    Size    Offset
  [INFO] -------  --------  -------  -----------  --------  -------  ------  --------
  [INFO]       0  .data     DATA     RW-- (0x03)  0x000000       14      14       104
  [INFO]       1  .text     TEXT     RWX- (0x07)  0x000100       24      96       118
  [INFO]       2  .symtab   SYMBOLS  ---- (0x00)  0x000200        6     120       214
  [INFO]       3  .strings  STRINGS  ---- (0x00)  0x000000        0     122       334
  [INFO] 
  [INFO] === Symbols ===
  [INFO] 
  [INFO] Name                    Section    Address    Type            Size  File                      Line    Content
  [INFO] ----------------------  ---------  ---------  ------------  ------  ------------------------  ------  ---------------
  [INFO] message                 .data      0x000000   string (2)        14  examples/hello-world.asm  1       "Hello, world!"
  [INFO] main                    .text      0x000100   function (3)       0  examples/hello-world.asm  4
  [INFO] outb                    .text      0x000110   function (3)       0  examples/hello-world.asm  10
  [INFO] writesn                 .text      0x000118   function (3)       0  examples/hello-world.asm  16
  [INFO] .__fn_writesn_loop      .text      0x00012C   function (3)       0  examples/hello-world.asm  27
  [INFO] .__fn_writesn_write_nl  .text      0x000140   function (3)       0  examples/hello-world.asm  33
  [INFO] 
  [INFO] === Disassemble ==
  [INFO] 
  [INFO]   Section .text
  [INFO]   0x000100 (0x00000004) li r0, 0x0000
  [INFO]   0x000104 (0x0000800D) call 0x0010
  [INFO]   0x000108 (0x00000004) li r0, 0x0000
  [INFO]   0x00010C (0x0000000B) int 0x0000
  [INFO]   0x000110 (0x000000E3) outb r0, r1
  [INFO]   0x000114 (0x0000000E) ret
  [INFO]   0x000118 (0x000000D4) push r1
  [INFO]   0x00011C (0x00000154) push r2
  [INFO]   0x000120 (0x00000054) push r0
  [INFO]   0x000124 (0x00000095) pop r2
  [INFO]   0x000128 (0x00040004) li r0, 0x0100
  [INFO]   0x00012C (0x00000842) lb r1, r2
  [INFO]   0x000130 (0x00006029) bz 0x000C
  [INFO]   0x000134 (0x0FFEC00D) call -0x0028
  [INFO]   0x000138 (0x00000096) inc r2
  [INFO]   0x00013C (0x0FFF6026) j -0x0014
  [INFO]   0x000140 (0x00002844) li r1, 0x000A
  [INFO]   0x000144 (0x0FFE400D) call -0x0038
  [INFO]   0x000148 (0x00003444) li r1, 0x000D
  [INFO]   0x00014C (0x0FFE000D) call -0x0040
  [INFO]   0x000150 (0x00000004) li r0, 0x0000
  [INFO]   0x000154 (0x00000095) pop r2
  [INFO]   0x000158 (0x00000055) pop r1
  [INFO]   0x00015C (0x0000000E) ret
  [INFO] 

As you can see, object file contains instructions, some additional data, list
of symbols, and some more, with labels replaced by dummy offsets. Offsets in
jump instructions make no sense yet because object file is not the finalized
binary - yet. For that, there's yet another tool:

.. code-block:: none

  ducky-ld -i examples/hello-world/hello-world.o -o examples/hello-world/hello-world

This command will take object file (or many of them), and produce one
:term:`binary` by merging code, data and other sections from all source object
files, and updates addresses used by instructions to retrieve data and to
perform jumps. You can inspect the resulting binary file using ``objdump`` tool
as well:

.. code-block:: none

  ducky-objdump -i examples/hello-world/hello-world -a

This should produce output very similar to the one you've already seen - not
much had changed, there was only one object file, only offsets used by ``call``
and ``j`` instructions are now non-zero, meaning they are now pointing to the
correct locations.


Running
^^^^^^^

Virtual machine configuration can get quite complicated, so I try to avoid too
many command line options, and opt for using configuration files. For this example,
there's one already prepared. Go ahead and try it:

.. code-block:: none

  ducky-vm --machine-config=examples/hello-world/hello-world.conf --set-option=bootloader:file=examples/hello-world/hello-world

There are two command-line options:

 - ``--machine-config`` tells VM where to find its configuration file,
 - ``--set-option`` modifies this configuration; this particular instance tells
   VM to set ``file`` option in section ``bootloader`` to path of our freshly
   built binary, ``examples/hello-world/hello-world``. Since I run examples
   during testing process, their config files lack this option since it changes
   all the time.

You should get output similar to this:

.. code-block:: none
  :linenos:

  1441740855.82 [INFO] Ducky VM, version 1.0
  1441740855.82 [INFO] mm: 16384.0KiB, 16383.5KiB available
  1441740855.82 [INFO] hid: basic keyboard controller on [0x0100] as device-1
  1441740855.83 [INFO] hid: basic tty on [0x0200] as device-2
  1441740855.83 [INFO] hid: basic terminal (device-1, device-2)
  1441740855.83 [INFO] snapshot: storage ready, backed by file ducky-snapshot.bin
  1441740855.83 [INFO] RTC: time 21:34:15, date: 08/09/15
  1441740855.83 [INFO] irq: loading routines from file interrupts
  1441740856.02 [INFO] binary: loading from from file examples/hello-world/hello-world
  1441740856.02 [INFO] #0:#0: CPU core is up
  1441740856.02 [INFO] #0:#0:   check-frames: yes
  1441740856.02 [INFO] #0:#0:   coprocessor: math
  1441740856.02 [INFO] #0: CPU is up
  Hello, world!
  1441740856.04 [INFO] #0:#0: CPU core halted
  1441740856.05 [INFO] #0: CPU halted
  1441740856.05 [INFO] snapshot: saved in file ducky-snapshot.bin
  1441740856.05 [INFO] Halted.
  1441740856.05 [INFO] 
  1441740856.05 [INFO] Exit codes
  1441740856.05 [INFO] Core      Exit code
  1441740856.06 [INFO] ------  -----------
  1441740856.06 [INFO] #0:#0             0
  1441740856.06 [INFO] 
  1441740856.06 [INFO] Instruction caches
  1441740856.06 [INFO] Core      Reads    Inserts    Hits    Misses    Prunes
  1441740856.06 [INFO] ------  -------  ---------  ------  --------  --------
  1441740856.06 [INFO] #0:#0       133         34      99        34         0
  1441740856.06 [INFO] 
  1441740856.06 [INFO] Core    Ticks
  1441740856.06 [INFO] ------  -------
  1441740856.06 [INFO] #0:#0   133
  1441740856.06 [INFO] 
  1441740856.06 [INFO] Executed instructions: 133 0.028670 (4639.0223/sec)
  1441740856.06 [INFO] 

And there, on line 16, between all that funny nonsenses, it is! :) The rest of
the output are just various notes about loaded binaries, CPU caches, nothing
important right now.

And that's it.
