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

  tools/as -i examples/hello-world.asm -o examples/hello-world.bin

This command will translate source code to instructions for VM. You can inspect the binary files using ``objdump`` tool:

.. code-block:: none

  tools/objdump -i examples/hello-world.bin -a

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

You can see internal section in the binary file, list of symbols, and disassembled instructions (with labels replaced by proper offsets).


Running
^^^^^^^

Virtual machine configuration can get quite complicated, so I try to avoid too many command line options, and opt for using configuration files. For this example, there's one already prepared. Go ahead and try it:

.. code-block:: none

  tools/vm --machine-config=examples/hello-world.conf -g --conio-stdout-echo=yes

There are two other command line options that deserve some explanation:

 - ``-g`` - by default, VM prepares itself, and waits for user to press ``Enter`` to actually start running the loaded programs. This option tells it to skip "press any key" phase and go ahead.
 - ``--conio-stdout-echo=yes`` - by default, your terminal is dedicated to output of VM itself, and output (and input, too) of running programs is handled by pseudoterminal (`ptty`), you can use e.g. ``screen`` to connect to this terminal and communicate with your programs. But this is waaaay to complicated for such a simple example like `Hello, world!`. All we want to see is one line, no need to tell our example anything. For such case there's a ``--conio-stdout-echo`` which, when set to ``yes``, will mirror output of your program to your terminal.

You should get output similar to this:

.. code-block:: none
  :linenos:

  #> [INFO] Loading IRQ routines from file interrupts.bin
  [INFO] Section    Address      Size  Flags                                 First page    Last page
  [INFO] ---------  ---------  ------  ----------------------------------  ------------  -----------
  [INFO] .data      0x010000        2  <SectionFlags: r=1, w=1, x=0, b=0>           256          256
  [INFO] .text      0x010100       64  <SectionFlags: r=1, w=1, x=1, b=0>           257          257
  [INFO] stack      0x010200      256  <SectionFlags: r=1, w=1, x=0, b=0>           258          258
  [INFO] 
  [INFO] Loading binary from file examples/hello-world.bin
  [INFO] Section    Address      Size  Flags                                 First page    Last page
  [INFO] ---------  ---------  ------  ----------------------------------  ------------  -----------
  [INFO] .data      0x020000       14  <SectionFlags: r=1, w=1, x=0, b=0>           512          512
  [INFO] .text      0x020100       96  <SectionFlags: r=1, w=1, x=1, b=0>           513          513
  [INFO] stack      0x020200      256  <SectionFlags: r=1, w=1, x=0, b=0>           514          514
  [INFO] 
  [INFO] #0: Booting...
  [INFO] #0:#0:  Booted
  [INFO] #0: Booted
  [INFO] Guest terminal available at /dev/pts/19
  Hello, world!
  [INFO] #0:#0:  Halted
  [INFO] VM snapshot save in ducky-snapshot.bin
  [INFO] Exit codes
  [INFO] Core      Exit code
  [INFO] ------  -----------
  [INFO] #0:#0             0
  [INFO] 
  [INFO] Instruction caches
  [INFO] Core      Reads    Inserts    Hits    Misses    Prunes
  [INFO] ------  -------  ---------  ------  --------  --------
  [INFO] #0:#0       119         26      93        26         0
  [INFO] 
  [INFO] Data caches
  [INFO] Core      Reads    Inserts    Hits    Misses    Prunes
  [INFO] ------  -------  ---------  ------  --------  --------
  [INFO] #0:#0       237        231     237         0         0
  [INFO] 

And there, on line 19, between all that funny nonsenses, it is! :) The rest of the output are just various notes about loaded binaries, CPU caches, nothing important right now - as I said, terminal is dedicated to VM itself.
