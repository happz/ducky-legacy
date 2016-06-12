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

Design principles
"""""""""""""""""

 - load and store operations are performed by dedicated instructions
 - memory-register transfers work with operands of different widths - 32-bit (`word`), 16-bit (`short`), and 8-bit (`byte`)
 - all memory-register transfers work with addresses that are aligned to the size of their operands (1 byte alignment - so no alignment at all - for byte-sized operands)
 - unless said otherwise, destination operand is the first one
 - when content of a register is changed by an instruction, several flags can be modified subsequently. E.g. when new value of register is zero, ``z`` flag is set.

Notes on documentation
""""""""""""""""""""""

 - ``rN`` refers to generaly any register, from ``r0`` up to ``r29`` - special registers are refered to by their common names (e.g. ``SP``).
 - ``rA``, ``rB`` refer to the first and the second instruction operand respectively and stand for any register.
 - ``<value>`` means immediate, absolute value. This covers both integers, specified as base 10 or base 16 integers, both positive and negative, and labels and addresses, specified as ``&label``
 - when instruction accepts more than one operand type, it is documented using ``|`` character, e.g. ``(rA|<value>)`` means either register or immediate value
 - immediate values are encoded in the instructions, therefore such value cannot have full 32-bit width. Each instruction should indicate the maximal width of immediate value that can be safely encoded, should you require grater values, please see ``li`` and ``liu`` instructions

.. toctree::
  :maxdepth: 2

  ducky_instruction_set.rst
  math_copro_instruction_set.rst


Memory
------


Memory model
^^^^^^^^^^^^

 - the full addressable memory is 4 GB, since the address bus is 32-bit wide, but it is quite unrealistic expectation. I usually stick to 24-bits for addresses, which leads to 16MB of main memory
 - memory is organized into pages of 256 bytes
   - each page can be restricted for read, write and execute operations


Memory layout
^^^^^^^^^^^^^

Exception Vector Table
""""""""""""""""""""""

Exception vector table (`EVT`), located in main memory, is by default located at address ``0x00000000``. ``EVT`` address can be set per CPU core, see control coprocessor docs for more. ``EVT`` is 256 bytes - 1 memory page - long, providing enough space for 32 entries. Typically, lower 16 entries are reserved for hardware interrupts, provided by devices, and upper 16 entries lead to software routines that deal with exceptions, and provide additional functionality for running code in form of software interrupts.

+------------------+------------------+
| ``IP`` - 32 bits | ``SP`` - 32 bits |
+------------------+------------------+

When CPU is interrupted - by hardware (device generates IRQ) or software (exception is detected, or program executes ``int`` instruction) interrupt - corresponding entry is located in ``EVT``, using interrupt ID as an index.


Stack
"""""

 - standard LIFO data structure
 - grows from higher addresses to lower
 - there is no pre-allocated stack, every bit of code needs to prepare its own if it intends to use instructions that operate with stack
 - when push'ing value to stack, ``SP`` is decreased by 4 (size of general register), and then value is stored on this address
 - each ``IVT`` provides its own stack pointer
