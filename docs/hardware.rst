Virtual hardware
================


CPU
---

Ducky VM can have multiple CPUs, each with multiple cores. Each core is
a 32-bit microprocessor, with 32 32-bit registers, connected to main memory.
It is equiped with MMU, and its own instruction cache.

CPU core can work in privileged and unprivileged modes, allowing use of
several protected instructions in privileged mode.


Registers
^^^^^^^^^

 - 32 32-bit registers
   - registers ``r0`` to ``r29`` are general purpose registers
   - ``r31`` is reserved, and used as a stack pointer register, ``SP`` - contains address of the last value pushed on stack
   - ``r30`` is reserved, and used as a frame pointer register, ``FP`` - contains content of ``SP`` in time of the last ``call`` or ``int`` instruction
 - ``flags`` register


Flags register
^^^^^^^^^^^^^^

``flags`` register can be considered as read-only value, since it is not possible to modify it using common bit operations or arithmetic instructions. However, its content reflect outcomes of executed instructions, therefore it is possible e.g. to modify it content using comparison instructions. It is also possible to inspect and modify it in exception service routine, where pre-exception ``flags`` are stored on the stack (and loaded when ESR ends).

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

CPU supports multiple instruction sets. The default one, `ducky`, is the main workhorse, suited for general coding, but other instruction sets can exist, e.g. coprocessor may use its own instruction set for its operations.

.. toctree::
  :maxdepth: 2

  ducky_instruction_set.rst
  math_copro_instruction_set.rst


Control coprocessor
-------------------

Control coprocessor (`CC`) is a coprocessor dedicated to control various runtime properties of CPU core. Using ``ctr`` and ``ctw`` instructions it is possible to inspect and modify these properties.


Control registers
^^^^^^^^^^^^^^^^^

CR0
"""

``cr0`` register contains so-called ``CPUID`` value which intendifies location of this CPU core in global CPU topology.

 - upper 16 bits contain index number of CPU this core belongs to
 - lower 16 bits contain index number of this core in the context of its parent CPU

There's always core with ``CPUID`` ``0x00000000``, since there's always at least one core present.

This register is read-only.


.. _CR1:

CR1
"""

``cr1`` register contains :ref:`EVT` address for this core. Be aware that *any* address is accepted, no aligment or any other restrictions are applied.


CR2
"""

``cr2`` register contains page table address for this core. Be aware that *any* address is accepted, no aligment or any other restrictions are applied.


CR3
"""

``cr3`` register provides access to several flags that modify behavior of CPU core.

+--------+----------------+------------------------------------------------------------+
| Mask   | Flag           | Usage                                                      |
+--------+----------------+------------------------------------------------------------+
| 0x00   | ``pt_enabled`` | If set, MMU consults all memory accesses with page tables. |
+--------+----------------+------------------------------------------------------------+
| 0x01   | ``jit``        | If set, JIT optimizations are enabled.                     |
+--------+----------------+------------------------------------------------------------+
| 0x02   | ``vmdebug``    | If set, VM will produce huge amount of debugging logs.     |
+--------+----------------+------------------------------------------------------------+

.. note::

  ``jit`` flag is read-only. It is controlled by options passed to Ducky when VM was created, and cannot be changed in runtime.

.. note::
  ``vmdebug`` flag is shared between all existing cores. Changing it on one core affects immediately all other cores.

.. note::
  ``vmdebug`` flag will not produce any debugging output if debug mode was disabled e.g. by not passing ``-d`` option to ``ducky-vm`` tool. If debug mode was allowed, changing this flag will control log level of VM.


.. _EVT:

Exception Vector Table
----------------------

Exception vector table (`EVT`) is located in main memory, by default at address ``0x00000000``, and provides core with routines that can help resolve some of exceptional states core can run into.

``EVT`` address can be set per CPU core, see :ref:`CR1`.

``EVT`` is 256 bytes - 1 memory page - long, providing enough space for 32 entries. Typically, lower 16 entries are reserved for hardware interrupts, provided by devices, and upper
16 entries lead to software routines that deal with exceptions, and provide additional functionality for running code in form of software interrupts.


Entry format
^^^^^^^^^^^^

+------------------+------------------+
| ``IP`` - 32 bits | ``SP`` - 32 bits |
+------------------+------------------+

When CPU is interrupted - by hardware (device generates IRQ) or software (exception is detected, or program executes ``int`` instruction) interrupt - corresponding entry is located in ``EVT``, using interrupt ID as an index.


.. _HDT:

Hardware Description Table
--------------------------

Hardware Description Table (`HDT`) is located in main memory, by default at address ``0x00000100``, and hardware setup of the machine.


Memory
------


Memory model
^^^^^^^^^^^^

 - the full addressable memory is 4 GB, since the address bus is 32-bit wide, but it is quite unrealistic expectation. I usually stick to 24-bits for addresses, which leads to 16MB of main memory
 - memory is organized into pages of 256 bytes
   - each page can be restricted for read, write and execute operations


Memory layout
^^^^^^^^^^^^^

Stack
"""""

 - standard LIFO data structure
 - grows from higher addresses to lower
 - there is no pre-allocated stack, every bit of code needs to prepare its own if it intends to use instructions that operate with stack
 - when push'ing value to stack, ``SP`` is decreased by 4 (size of general register), and then value is stored on this address
 - each ``EVT`` provides its own stack pointer
