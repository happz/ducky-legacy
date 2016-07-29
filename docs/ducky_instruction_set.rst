Ducky instruction set
=====================


Design principles
^^^^^^^^^^^^^^^^^

 - basic data unit is `a word` - 4 bytes, 32 bits. Other units are `short` - 2 bytes, 16 bits - and `byte` - 1 byte, 8 bits. Instructions often have variants for different data units, distinguished by a suffix (`w` for words, `s` for shorts, and `b` for single bytes)
 - load and store operations are performed by dedicated instructions
 - memory-register transfers work with addresses that are aligned to the size of their operands (1 byte alignment - so no alignment at all - for byte operands)
 - unless said otherwise, destination operand is the first one
 - when content of a register is changed by instruction, several flags can be modified subsequently. E.g. when new value of register is zero, ``z`` flag is set.


Notes on documentation
^^^^^^^^^^^^^^^^^^^^^^

 - ``rN`` refers to generaly any register, from ``r0`` up to ``r29`` - special registers are refered to by their common names (e.g. ``SP``).
 - ``rA``, ``rB`` refer to the first and the second instruction operand respectively and stand for any register.
 - ``<value>`` means immediate, absolute value. This covers both integers, specified as base 10 or base 16 integers, both positive and negative, and labels and addresses, specified as ``&label``
 - when instruction accepts more than one operand type, it is documented using ``|`` character, e.g. ``(rA|<value>)`` means either register or immediate value
 - immediate values are encoded in the instructions, therefore such value cannot have full 32-bit width. Each instruction should indicate the maximal width of immediate value that can be safely encoded, should you require grater values, please see ``li`` and ``liu`` instructions


Stack frames
^^^^^^^^^^^^

Several instructions transfer control to other parts of program, with possibility of returning back to the previous spot. It is done by creating a `stack frame`. When stack frame is created, CPU performs these steps:

 - ``IP`` is pushed onto the stack
 - ``FP`` is pushed onto the stack
 - ``FP`` is loaded with value of ``SP``

Destroying stack frame - reverting the steps above - effectively transfers control back to the point where the subroutine was called from.


Arithmetic
^^^^^^^^^^

All arithmetic instructions take at least one operand, a register. In case of binary operations, the second operand can be a register, or an immediate value (15 bits wide, sign-extended to 32 bits). The result is always stored in the first operand.

``add rA, (rB|<value>)``

``dec rA``

``inc rA``

``mul rA, (rB|<value>)``

``sub rA, (rB|<value>)``


Bitwise operations
^^^^^^^^^^^^^^^^^^

All bitwise operations - with exception of ``not`` - take two operands, a register, and either another register or an immediate value (15 bits wide, sign-extended to 32 bits). The result is always stored in the first operand.

``and rA, (rB|<value>)``

``not rA``

``or rA, (rB|<value>)``

``shiftl rA, (rB|<value>)``

``shiftr rA, (rB|<value>)``

``shiftrs rA, (rB|<value>)``

``xor rA, (rB|<values>)``


Branching instructions
^^^^^^^^^^^^^^^^^^^^^^

Branching instructions come in form ``<inst> (rA|<address>)``. If certain conditions are met, branching instruction will perform jump by adding value of the operand to the current value of ``PC`` (which, when instruction is being executed, points *to the next instruction* already). If the operand is an immediate address, it is encoded in the instruction as an immediate value (16 bit wide, sign-extended to 32 bits). This limits range of addresses that can be reached using this form of branching instructions.

Branching instructions do not create new stack frame.

Unconditional branching
"""""""""""""""""""""""

``j (rA|<value>)``

Conditional branching
"""""""""""""""""""""

+-------------+-------------------------+
| Instruction | Jump when ...           |
+-------------+-------------------------+
| ``be``      | ``e = 1``               |
+-------------+-------------------------+
| ``bne``     | ``e = 0``               |
+-------------+-------------------------+
| ``bs``      | ``s = 1``               |
+-------------+-------------------------+
| ``bns``     | ``s = 0``               |
+-------------+-------------------------+
| ``bz``      | ``z = 1``               |
+-------------+-------------------------+
| ``bnz``     | ``z = 0``               |
+-------------+-------------------------+
| ``bo``      | ``o = 1``               |
+-------------+-------------------------+
| ``bno``     | ``o = 0``               |
+-------------+-------------------------+
| ``bg``      | ``e = 0`` and ``s = 0`` |
+-------------+-------------------------+
| ``bge``     | ``e = 1`` or ``s = 0``  |
+-------------+-------------------------+
| ``bl``      | ``e = 0`` and ``s = 1`` |
+-------------+-------------------------+
| ``ble``     | ``e = 1`` or ``s = 1``  |
+-------------+-------------------------+

Conditional setting
"""""""""""""""""""

All conditional setting instructions come in form ``<inst> rA``. Depending on relevant flags, ``rA`` is set to ``1`` if condition is evaluated to be true, or to ``0`` otherwise.

For flags relevant for each instruction, see branching instruction with the same suffix (e.g. ``setle`` evaluates the same flags with the same result as ``ble``).

+-------------+
| Instruction |
+-------------+
| ``sete``    |
+-------------+
| ``setne``   |
+-------------+
| ``setz``    |
+-------------+
| ``setnz``   |
+-------------+
| ``seto``    |
+-------------+
| ``setno``   |
+-------------+
| ``sets``    |
+-------------+
| ``setns``   |
+-------------+
| ``setg``    |
+-------------+
| ``setge``   |
+-------------+
| ``setl``    |
+-------------+
| ``setle``   |
+-------------+


Comparing
"""""""""

Two instructions are available for comparing of values. Compare their operands and sets corresponding flags. The second operand can be either a register or an immediate value (15 bits wide).

``cmp rA, (rB|<value>)`` - immediate value is sign-extended to 32 bits.

``cmpu rA, (rB|<value>)`` - treat operands as unsigned values, immediate value is zero-extended to 32 bits.


Interrupts
^^^^^^^^^^

Delivery
""""""""

If flag ``hwint_allowed`` is unset, no hardware IRQ can be accepted by CPU and stays queued. All queued IRQs will be delivered as soon as flag is set.

``cli`` - clear ``hwint`` flag

``sti`` - set ``hwint`` flag

In need of waiting for external events it is possible to suspend CPU until the next IRQ is delivered.

``idle`` - wait until next IRQ

Invocation
""""""""""

Any interrupt service routine can be invoked by means of special instruction. When invoked several events take place:

 - ``SP`` is saved in temporary space
 - ``IP`` and ``SP`` are set to values that are stored in ``EVT`` in the corresponding entry
 - important registers are pushed onto new stack (in this order): old ``SP``, ``flags``
 - new stack frame is created
 - privileged mode is enabled
 - delivery of hardware interrupts is disabled

When routine ends (via ``retint``), these steps are undone, and content of saved registers is restored.

``int (rA|<index>)``

``retint`` - return from interrupt routine


Inter-processor interrupts (``IPI``) can be delivered to other processors, via dedicated instruction, similar to ``int`` but specifying CPUID of target core in the first operand.

``ipi rA, (rB|<index>)``


Routines
^^^^^^^^

When routine is called, new stack frame is created, and CPU continues with instructions pointed to by the first operand. For its meaning (and limitations) see `Branching instructions`.

``call (rA|<address>)``

``ret``


Stack
^^^^^

``pop rA``

``push (rA|<value>)``


Miscellaneous
^^^^^^^^^^^^^

``nop`` - do absolutely nothing

``hlt (rA|<value>)`` - Halt CPU and set its exit code to specified value.

``rst`` - reset CPU state. All flags cleared, ``privileged = 1``, ``hwint_allowed = 0``, all registers set to ``0``

``mov rA, rB`` - copy value of ``rB`` into ``rA``

``swp rA, rB`` - swap content of two registers

``sis <value>`` - switch instruction set to a different one


Memory access
^^^^^^^^^^^^^

Address operand - ``{address}`` - can be specified in different ways:

 - ``rA`` - address is stored in register
 - ``rA[<offset>]`` - address is computed by addition of ``rA`` and ``offset``. ``offset`` can be both positive and negative. ``fp`` and ``sp`` can be also used as ``rA``. ``<offset>`` is an immediate value, 15 bits wide, sign-extended to 32 bits.

Read
""""

``lw rA, {address}`` - load word from memory

``ls rA, {address}`` - load short from memory

``lb rA, {address}`` - load byte from memory

Write
"""""

``stw {address}, rA``

``sts {address}, rA`` - store lower 2 bytes of ``rA``

``stb {addres}, rA`` - store lower byte of ``rA``

Constants
^^^^^^^^^

Instructions for filling registers with values known in compile time.

``li rA, <constant>`` - load ``constant`` into register. ``constant`` is encoded into instruction as an immediate value (20 bits wide, sign-extended to 32 bits)

``liu rA, <constant>`` - load ``constant`` into the upper half of register. ``constant`` is encoded into instruction as an immediate value (20 bits wide immediate, only lower 16 bits are used)

``la rA, <constant>`` - load ``constant`` into the register. ``constant`` is an immediate value (20 bits wide, sign-extended to 32 bits), and is treated as an offset from the current value of ``PC`` - register is loaded with the result of ``PC + constant``.

Compare-and-swap
""""""""""""""""

``cas rA, rB, rC`` - read word from address in register ``rA``. Compare it with value in register ``rB`` - if both are equal, take content of ``rC`` and store it in memory on address ``rA``, else store memory value in ``rB``.
