VM Configuration file
=====================


Number of available options can easily get quite high, especially when different devices come into play, and setting all of them on command line is not very clear. To ease this part of VM processes, user can create a configuration file. Syntax is based on Python's ``ConfigParser`` or Windows ``.ini`` configuration files. It consists of sections, setting options for different subsystems (VM, CPUs, ...). You can find few configuration files in ``examples/`` directory.

When option takes an address as an argument, address can be specified either using decimal or hexadecimal base. Usually, the absolute address is necessary when option is not binary-aware, yet some options are tied closely to particular binary, such options can also accept name of a symbol. Option handling code will try to find corresponding address in binary's symbol table. This is valid for both command-line options and configuration files.



[machine]
---------

cpus
^^^^

Number of separate CPUs.

``int``, default ``1``


cores
^^^^^

Number of cores per CPU.

``int``, default ``1``


interrupt-routines
^^^^^^^^^^^^^^^^^^

Path to binary with interrupt service routines.

``str``, optional - if VM has no use for interrupts (no devices, binary handles everything), there's no need for IVT


[memory]
--------

size
^^^^

Memory size in bytes.

``int``, default ``0x1000000``


force-aligned-access
^^^^^^^^^^^^^^^^^^^^

When set, unaligned memory access will lead to exception.

``bool``, default ``yes``


[cpu]
-----

math-coprocessor
^^^^^^^^^^^^^^^^

When set, each CPU core will have its own math coprocessor.

``bool``, default ``no``


inst-cache
^^^^^^^^^^

Number of slots in instruction cache.

``int``, default ``256``


data-cache-enabled
^^^^^^^^^^^^^^^^^^

When set, each CPU core will have its own data cache.

``bool``, default ``yes``

data-cache-driver
^^^^^^^^^^^^^^^^^

Data cache implementation, one of ``python`` or ``native``.

``str``, default ``python``


data-cache-size
^^^^^^^^^^^^^^^

Number of slots in data cache.

``int``, default ``8192``


check-frame
^^^^^^^^^^^

When set, CPU cores will check if stack frames were cleaned properly when ``ret`` or ``iret`` is executed.

``bool``, default ``yes``


ivt-address
^^^^^^^^^^^

Address of interrupt vector table.

``int``, default ``0x000000``


[binary-N]
----------

Each section starting with ``binary-`` tells VM what binary is supposed to run, and its properties.

file
^^^^

Path to binary file.

``str``, required


entry
^^^^^

Start execution at this address.

``address``, default ``main``


[device-N]
----------

Each section starting with ``device-`` tells VM to create virtual device, and provide it to running binaries. Device sections have few options, common for all kinds of devices, and a set of options, specific for each different device or driver.

klass
^^^^^

Device class - arbitrary string, describing family of devices. E.g. I use ``input`` for devices processing user input (e.g. keyboard controllers).

``str``, required


driver
^^^^^^

Python class that *is* the device driver.

``str``, required


master
^^^^^^

If set, ``master`` is superior device, with some responsibilities over its subordinates.

``str``, optional
