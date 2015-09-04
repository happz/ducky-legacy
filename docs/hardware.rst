Virtual hardware
================


CPU
---

Ducky VM can have multiple CPUs, each with multiple cores. Each core is a 16-bit microprocessor, with 32-bit wide fixed instruction set, 13 working and 6 special registers, and access to main memory.

CPU core can work in privileged and unprivileged modes, allowing use of several protected instructions in privileged mode.


Registers
^^^^^^^^^

 - 13 16-bit general purpose registers, named ``r0`` to ``r12``
 - 6 other registers with special purpose
   - ``CS`` - segment 16-bit register, contains index of current code segment
   - ``DS`` - segment 16-bit register, contains index of current data segment
   - ``Flags`` - 16-bit flag register
   - ``SP`` - 16-bit stack pointer, contains address of the last push'ed value on stack
   - ``FP`` - 16-bit frame pointer, contains content of ``SP`` in time of the last ``call`` or ``int`` instruction
   - ``IP`` - 16-bit instruction pointer, contains address of **next** instruction to be executed

Special registers are protected and cannot be modified by standard means (``push flags; <modify flags>; pop flags``) when CPU is in user mode


Segment registers
^^^^^^^^^^^^^^^^^

 - program is loaded into its own code segment, and owns its own data segment. Their numbers are stored in registers ``CS``, ``DS`` respectively
 - before every memory accesses the final address is produced by multiplying proper segment number and adding requested address
 - ``CS`` and ``DS`` registers are 16 bits wide but only lower byte is relevant


Flags register
^^^^^^^^^^^^^^

+--------+----------------+-------------------------------------------------------------------------------------+
| Mask   | Flags          | Usage                                                                               |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x00   | ``privileged`` | If set, CPU runs in privileged mode, and usage of protected instructions is allowed |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x01   | ``hwint``      | If set, HW interrupts are allowed to interrupt                                      |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x04   | ``e``          | Set if the last two compared registers were equal                                   |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x08   | ``z``          | Set if the last arithmetic operation produced zero                                  |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x10   | ``o``          | Set if the last arithmetic operation overflown                                      |
+--------+----------------+-------------------------------------------------------------------------------------+
| 0x11   | ``s``          | Set if the last arithmetic operation produced negative result                       |
+--------+----------------+-------------------------------------------------------------------------------------+


Instruction set
^^^^^^^^^^^^^^^

CPU supports multiple instruction set. The main one, `ducky`, is the main workhorse, suited for general coding, but other instruction sets can exist, e.g. coprocessor may use its own instruction set for its operations.

Design principles
"""""""""""""""""

 - load and store operations are performed by dedicated instructions
 - all memory-register transfers work with 16-bit operands, 8-bit operands are handled by special instructions when necessary
 - all memory-register transfers work with addresses that are aligned to the size of their operands - 2 bytes for 16-bit operands, 1 byte (so no alignment at all) for 8-bit operands
 - in most cases, destination operand is the first one. Exceptions are instructions that work with IO ports.
 - when content of a register is changed by instruction, several flags can be modified subsequently. E.g. when new value of register is zero, ``z`` flag is set.

Notes on documentation
""""""""""""""""""""""

 - ``rN`` refers to generaly any register, from ``r0`` up to ``r12`` - special registers are refered to by their common names (e.g. ``SP``).
 - ``rA``, ``rB`` refer to the first and the second instruction operand respectively and stand for any register.
 - ``<value>`` means immediate, absolute value. This covers both integers, specified as base 10 or base 16 integers, both positive and negative, and labels and addresses, specified as ``&label``
 - when instruction accepts more than one operand type, it is documented using ``|`` character, e.g. ``(rA|<value>)`` means either register or immediate value

.. toctree::
  :maxdepth: 2

  ducky_instruction_set.rst
  math_copro_instruction_set.rst


Cache
^^^^^

Every memory access (fetching instructions, read/write of other data) goes through a cache. Separate instruction and data cache exist for each CPU core, both having a limited size and trackking access to support LRU replacement policy.

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

 - the full addressable memory is 16MB
 - each program has its own code and data segment
   - they are isolated from each other - CS/DS registers are protected in user mode
   - each segment can be addressed by unsigned 16-bit address, therefore 256 different segments available
 - memory is organized into pages of 256 bytes
   - each page can be restricted for read, write and execute operations


Memory layout
^^^^^^^^^^^^^

Interrupt Vector tables
"""""""""""""""""""""""

There are two separate interrupt vector tables (`IVT`), located in main memory, in segment ``0``. Each table is 256 bytes long, enough for 64 entries. Each entry has the same layout:

+-----------------+-----------------+------------------+
| ``cs`` - 8 bits | ``ds`` - 8 bits | ``ip`` - 16 bits |
+-----------------+-----------------+------------------+

 - IRQ (hardware interrupts) table starts by default at ``0x000000``
 - INT (software interrupts) table starts by default at ``0x000100``


Stack
"""""

 - standard LIFO data structure
 - placed in data segment
 - grows from higher addresses to lower
 - 1 page is allocated for stack of each loaded binary right now but this will be tweakable
 - when push'ing value to stack, ``sp`` is decreased by 2 and then value is stored on this address
 - each interrupt routine gets its own stack, allocated specificaly for its invocation from data segment, stored in interrupt routine's IVT entry
