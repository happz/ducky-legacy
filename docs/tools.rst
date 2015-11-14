Tools
=====


Ducky comes with basic toolchain necessary for development of complex programs. One piece missing is the C cross-compiler with simple C library but this issue will be resolved one day.


Common options
--------------

All tools accept few common options:

``-q, --quiet``
^^^^^^^^^^^^^^^

Lower verbosity level by one. By default, it is set to `warnings`, more quiet levels are `error` and `critical`.


``-v, --verbose``

Increase verbosity level by one. By default, it is set to `warnings`, more verbose levels are `info` and `debug`. `debug` level is not available for ``duckt-vm`` unless ``-d`` option is set.


``-d, --debug``
^^^^^^^^^^^^^^^

Set logging level to `debug` immediately. ``ducky-vm`` also requires this option to even provide any debugging output - it is not possible to emit `debug` output by setting ``-v`` enough times if ``-d`` is not specified on command-line.


When option takes an address as an argument, address can be specified either using decimal or hexadecimal base. Usually, the absolute address is necessary when option is not binary-aware, yet some options are tied closely to particular binary, such options can also accept name of a symbol. Option handling code will try to find corresponding address in binary's symbol table. This is valid for both command-line options and configuration files.


as
--

Assembler. Translates *assembler files* (``.asm``) to *object files* (``.o``) - files containing bytecode, symbols information, etc.


Options
^^^^^^^

``-i FILE``
"""""""""""

Take assembly ``FILE``, and create an object file from its content. It can be specified multiple times, each input file will be processed.


``-o FILE``
"""""""""""

Write resulting object data into ``FILE``.

This options is optional. If no ``-o`` is specified, ``ducky-as`` will then create output file for each input one by replacing its suffix by ``.o``. If it is specified, number of ``-o`` options must match the number of ``-i`` options.


``-f``
""""""

When output file exists already, ``ducky-as`` will refuse to overwrite it, unless ``-f`` is set.


``-D VAR``
""""""""""

Define name, passed to processed assembly sources. User can check for its existence in source by ``.ifdef``/``.ifndef`` directives.


``-I DIR``
""""""""""

Add ``DIR`` to list of directories that are searched for files, when ``.include`` directive asks assembler to process additional source file.


``-m, --mmapable-sections``
"""""""""""""""""""""""""""

Create object file with sections that can be loaded using ``mmap()`` syscall. This option can save time during VMstartup, when binaries can be simply mmapped into VM's memory space, but it also creates larger binary files because of the alignment of sections in file.


``-w, --writable-sections``

By default, ``.text`` and ``.rodata`` sections are read-only. This option lowers this restriction, allowing binary to e.g. modify its own code.


ld
--

Linker. Takes (one or multiple) *object files* (``.o``) and merges them into one, *binary*, which can be executed by VM.


Options
^^^^^^^


``-i FILE``
"""""""""""

Take object ``FILE``, and create binary file out of it. It can be specified multiple times, all input files will be processed into one binary file.


``-o FILE``
"""""""""""

Output file.


``-f``
""""""

When output file exists already, ``ducky-ld`` will refuse to overwrite it, unless ``-f`` is set.


``--section-base=SECTION=ADDRESS``
""""""""""""""""""""""""""""""""""

Linker tries to merge all sections into a binary in a semi-random way - it can be influenced by order of sections in source and object files, and order of input files passed to linker. It is in fact implementation detail and can change in the future. If you need specific section to have its base set to known address, use this option. Be aware that linker may run out of space if you pass conflicting values, or force sections to create too small gaps between each other so other sections would not fit in.


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

.. toctree::
  :maxdepth: 1

  config-file.rst


Options
^^^^^^^


``--machine-config=PATH``
"""""""""""""""""""""""""

Specify ``PATH`` to VM configuration file. For its content, see :doc:`config-file`.


``--set-option=SECTION:OPTION=VALUE``
"""""""""""""""""""""""""""""""""""""
``--add-option=SECTION:OPTION=VALUE``
"""""""""""""""""""""""""""""""""""""

These two options allow user to modify the content of configuration file, by adding of new options or by changing the existing ones.

Lets have (incomplete) config file ``vm.conf``:

.. code-block:: none

  [machine]
  cpu = 1
  core = 1

  [binary-0]

You can use it to run different binaries without having separate config file for each of them, just by telling ``ducky-vm`` to load configuration file, and then change one option:

.. code-block:: none

  $ ducky-vm --machine-config=vm.conf --add-option=binary-0:file=<path to binary of your choice>

Similarly, you can modify existing options. Lets have (incomplete) config file ``vm.conf``:

.. code-block:: none

  [machine]
  cpus = 1
  cores = 1

  [binary-0]
  file = some/terminal/app

  [device-1]
  klass = input
  driver = ducky.devices.keyboard.KeyboardController
  master = device-3

  [device-2]
  klass = output
  driver = ducky.devices.tty.TTY
  master = device-3

  [device-3]
  klass = terminal
  driver = ducky.devices.terminal.StandardIOTerminal
  input = device-1
  output = device-2

Your ``app`` will run using VM's standard IO streams for input and out. But you may want to start it with a different kind of terminal, e.g. PTY one, and attach to it using ``screen``:

.. code-block:: none

  $ ducky-vm --machine-config=vm.conf --set-option=device-3:driver=ducky.devices.terminal.StandalonePTYTerminal


``--enable-device=DEVICE``
""""""""""""""""""""""""""
``--disable-device=DEVICE``
"""""""""""""""""""""""""""

Shortcuts for ``--set-option=DEVICE:enabled=yes`` and ``--set-option=DEVICE:enabled=no`` respectively.


``--poke=ADDRESS:VALUE:LENGTH``
"""""""""""""""""""""""""""""""

``poke`` option allows modification of VM's memory after all binaries and resources are loaded, just before the VM starts execution of binaries. It can be used for setting runtime-specific values, e.g. argument for a binary.

Consider a simple binary, running a loop for specified number of iterations:

.. code-block: gas

    .include "defs.asm"

    .data
    .type loops, int
    .int 10

    .text
  main:
    li r0, &loops
    lw r0, r0
  loop:
    bz &quit
    dec r0
    j &loop
  quit:
    int $INT_HALT

By default, 10 iterations are hard-coded into binary. If you want to termporarily change number of iterations, it's not necessary to recompile binary. By default, this binary, being the only one running, would get segment ``0x02``, it's ``.data`` section was mentioned first, therefore its base address will be ``0x0000``, leading to ``loops`` having absolute address ``0x020000``. Then:

.. code-block:: none

  $ ducky-vm --machine-config=vm.conf --poke=0x020000:100:2

will load binary, then modify its ``.data`` section by changing value at address ``0x020000`` to ``100``, which is new number of iterations. Meta variable ``LENGTH`` specifies number of bytes to overwrite by ``poke`` value, and ``poke`` will change exactly ``LENGTH`` bytes - if ``VALUE`` cannot fit into available bits, exceeding bits of ``VALUE`` are masked out, and ``VALUE`` that can fit is zero-extended to use all ``LENGTH`` bytes.


``--stdio-console``
"""""""""""""""""""

Enable console terminal with stdin and stdout as its IO streams. User can then enter commands in via the keyboard, while VM and its binaries use e.g. stand-alone pty terminals.


``-g, --go-on``
"""""""""""""""

By default, ``ducky-vm`` creates a VM and boots it, but before handing the constrol to it, ``ducky-vm`` will ask user to press any key. ``-g`` option tells ``ducky-vm`` to skip this part, and immediately start execution of binaries.
