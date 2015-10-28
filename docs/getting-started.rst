Getting started
===============


Installing
----------

There's no pip package right now, you can install Ducky by checking out the sources::

  git clone https://github.com/happz/ducky.git
  cd ducky
  python setup.py

After this, you should have the ``ducky`` module on your path::

  >>> import ducky
  >>> ducky.__version__
  '1.0'


Prerequisites
-------------

Ducky runs with **python 2.6** - python3 is **NOT** yet supported (it's on my TODO list though). There are few other dependencies, ``setup.py`` should take care of them autmatically.


"Hello, world!" tutorial
------------------------

Let's try out the "Hello, world!" example. It's a simple program that just prints out the well-known message.


Source code
^^^^^^^^^^^

Source is located in ``examples`` directory. If you check it out, it's a plain and simple assembler:

.. code-block:: gas

    .type message, string
    .string "Hello, world!"

  main:
    li r0, &message
    call &writesn
    li r0, 0
    int 0

  outb:
    ; > r0: port
    ; > r1: byte
    outb r0, r1
    ret

  writesn:
    ; > r0: string address
    ; ...
    ;   r0: port
    ;   r1: current byte
    ;   r2: string ptr
    push r1
    push r2
    push r0
    pop r2
    li r0, 0x100
  .__fn_writesn_loop:
    lb r1, r2
    bz &.__fn_writesn_write_nl
    call &outb
    inc r2
    j &.__fn_writesn_loop
  .__fn_writesn_write_nl:
    ; \n
    li r1, 0xA
    call &outb
    ; \r
    li r1, 0xD
    call &outb
    li r0, 0
    pop r2
    pop r1
    ret

It's a little bit more structured that necessary, just for educational purposes.


Binary
^^^^^^

Virtual machine needs binary (or bytecode, as you wish...) code, and there's a tool for it:

.. code-block:: none

  ducky-as -i examples/hello-world/hello-world.asm -o examples/hello-world/hello-world.o

This command will translate source code to object file, containing instructions for VM and other resources. You can inspect the object file using ``objdump`` tool:

.. code-block:: none

  ducky-objdump -i examples/hello-world/hello-world.o -a

This should produce output similar to this one:

.. code-block:: none

  [INFO] Input file: examples/hello-world.bin
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

You can see internal sections in the object file, list of symbols, and disassembled instructions, with labels replaced by dummy offsets. Offsets in jump instructions make no sense yet because object file is not the finalized binary - yet. For that, there's another tool:

.. code-block:: none

  ducky-ld -i examples/hello-world/hello-world.o -o examples/hello-world/hello-world

This command will take object file (or many of them), and produce one binary by merging code, data and sections in object files, and updates addresses used by instructions to retrieve data and to perform jumps. You can inspect the binary file using ``objdump`` tool, too:

.. code-block:: none

  ducky-objdump -i examples/hello-world/hello-world -a

This should produce output very similar to the one you've already seen - not much had changed, there was only one object files, only offsets used by ``call`` and ``j`` instructions are now non-zero, meaning they are now pointing to the correct locations.

Oh, and you will need basic interrupt routines - no need to invent them yourself for "Hello, world!" example, just run this:

.. code-block:: none

  make interrupts


Running
^^^^^^^

Virtual machine configuration can get quite complicated, so I try to avoid too many command line options, and opt for using configuration files. For this example, there's one already prepared. Go ahead and try it:

.. code-block:: none

  ducky-vm --machine-config=examples/hello-world/hello-world.conf -g

There are two other command line options that deserve some explanation:

 - ``-g`` - by default, VM prepares itself, and waits for user to press ``Enter`` to actually start running the loaded binaries. This option tells it to skip "press any key" phase and go ahead.

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
  1441740856.02 [INFO] #0:#0:   cache: 1024 DC slots, 256 IC slots
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
  1441740856.06 [INFO] Data caches
  1441740856.06 [INFO] Core      Reads    Inserts    Hits    Misses    Prunes
  1441740856.06 [INFO] ------  -------  ---------  ------  --------  --------
  1441740856.06 [INFO] #0:#0        93        173      85         8         0
  1441740856.06 [INFO] 
  1441740856.06 [INFO] Core    Ticks
  1441740856.06 [INFO] ------  -------
  1441740856.06 [INFO] #0:#0   133
  1441740856.06 [INFO] 
  1441740856.06 [INFO] Executed instructions: 133 0.028670 (4639.0223/sec)
  1441740856.06 [INFO] 

And there, on line 15, between all that funny nonsenses, it is! :) The rest of the output are just various notes about loaded binaries, CPU caches, nothing important right now - as I said, terminal is dedicated to VM itself.
