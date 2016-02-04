Virtual hardware
================


CPU
---

Ducky VM can have multiple CPUs, each with multiple cores. Each core is
a 32-bit microprocessor, with 32 32-bit registers, connected to main memory.
It is equiped with MMU, and its own optional data and instruction caches.

CPU core can work in privileged and unprivileged modes, allowing use of
several protected instructions in privileged mode.


Registers
^^^^^^^^^

 - 32 32-bit registers
   - registers ``r0`` to ``r28`` are general purpose registers
   - ``r30`` is reserved, and used as a stack pointer register, ``SP`` - contains address of the last push'ed value on stack
   - ``r29`` is reserved, and used as a frame pointer register, ``FP`` - contains content of ``SP`` in time of the last ``call`` or ``int`` instruction
   - ``r31`` is reserved, and used as a instruction pointer register, ``IP`` - contains address of **next** instruction to be executed
 - ``flags`` register

``IP`` and ``flags`` registers are protected, and cannot be modified by standard means (``push flags; <modify flags>; pop flags``) when CPU is in user mode


Flags register
^^^^^^^^^^^^^^

+--------+-------------------+-------------------------------------------------------------------------------------+
| Mask   | Flags             | Usage                                                                               |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x00   | ``privileged``    | If set, CPU runs in privileged mode, and usage of protected instructions is allowed |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x01   | ``hwint_allowed`` | If set, HW interrupts can be delivered to this core                                 |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x04   | ``e``             | Set if the last two compared registers were equal                                   |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x08   | ``z``             | Set if the last arithmetic operation produced zero                                  |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x10   | ``o``             | Set if the last arithmetic operation overflown                                      |
+--------+-------------------+-------------------------------------------------------------------------------------+
| 0x20   | ``s``             | Set if the last arithmetic operation produced negative result                       |
+--------+-------------------+-------------------------------------------------------------------------------------+


Instruction set
^^^^^^^^^^^^^^^

CPU supports multiple instruction set. The default one, `ducky`, is the main workhorse, suited for general coding, but other instruction sets can exist, e.g. coprocessor may use its own instruction set for its operations.

Design principles
"""""""""""""""""

 - load and store operations are performed by dedicated instructions
 - all memory-register transfers work with 32-bit operands, 16-bit and 8-bit operands are handled by special instructions when necessary
 - all memory-register transfers work with addresses that are aligned to the size of their operands (1 byte alignment - so no alignment at all - for 8-bit operands)
 - in most cases, destination operand is the first one. Exceptions are instructions that work with IO ports.
 - when content of a register is changed by an instruction, several flags can be modified subsequently. E.g. when new value of register is zero, ``z`` flag is set.

Notes on documentation
""""""""""""""""""""""

 - ``rN`` refers to generaly any register, from ``r0`` up to ``r28`` - special registers are refered to by their common names (e.g. ``SP``).
 - ``rA``, ``rB`` refer to the first and the second instruction operand respectively and stand for any register.
 - ``<value>`` means immediate, absolute value. This covers both integers, specified as base 10 or base 16 integers, both positive and negative, and labels and addresses, specified as ``&label``
 - when instruction accepts more than one operand type, it is documented using ``|`` character, e.g. ``(rA|<value>)`` means either register or immediate value

.. toctree::
  :maxdepth: 2

  ducky_instruction_set.rst
  math_copro_instruction_set.rst


Cache
^^^^^

Every memory access (fetching instructions, read/write of other data) goes through a cache. Separate instruction and data cache exist for each CPU core, both having a limited size and tracking access to support LRU replacement policy.

Instruction cache
"""""""""""""""""

Since modification of running code is not supported yet, instruction cache does not care about synchronization or coherency, and simply reads data from main memory, and stores and provides already decoded instructions.

Data cache
""""""""""

Data cache, on the other hand, have to guarantee cache consistency and coherency between all caches of all CPU cores, and all other devices attached to the VM a manipulating memory. So far, all CPU cores should share the consistent view of memory content, regardles on executed instructions, unless MMIO, devices with direct memory access or external write to a mmaped file are involved. Both MMIO and direct memory access devices can use uncacheable memory pages for their working buffers to overcome this limitation, or make use of :py:class:`ducky.cpu.CPUCacheController` and its ``release_*_references`` methods to flush all necessary caches. Solving external writes into a shared, mmaped file is not possible without additional signal mechanism.


Memory
------


Memory model
^^^^^^^^^^^^

 - the full addressable memory is 4 GB, but it is quite unrealistic expectation. I usually stick to 24-bits for addresses, which leads to 16MB of main memory
 - memory is organized into pages of 256 bytes
   - each page can be restricted for read, write and execute operations


Memory layout
^^^^^^^^^^^^^

Interrupt Vector table
""""""""""""""""""""""

Interrupt vector table (`IVT`), located in main memory, is by default located at address ``0x00000000``. ``IVT`` address can be set per CPU core. ``IVT`` is 256 bytes long, providing enough space for 64 entries. Typically, lower 32 entries are reserved for hardware interrupts, provided by devices, and upper 32 entries leads to software routines that provide additional functionality for binaries. Each entry has the same layout:

+------------------+------------------+
| ``IP`` - 32 bits | ``SP`` - 32 bits |
+------------------+------------------+

When CPU is interrupted - by hardware (device generates interrupt) or software (program executes ``int`` instruction) interrupt - corresponding entry is located in ``IVT``, using interrupt ID as an index.


Stack
"""""

 - standard LIFO data structure
 - grows from higher addresses to lower
 - there is no pre-allocated stack, every bit of code needs to prepare its own if it intends to use instructions that operate with stack
 - when push'ing value to stack, ``SP`` is decreased by 4 (size of general register), and then value is stored on this address
 - each ``IVT`` provides its own stack pointer
