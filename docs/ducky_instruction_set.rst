Ducky instruction set
=====================

This page descriped the main instruction set of Ducky VM.


Arithmetic
^^^^^^^^^^

All arithmetic instructions take at least one operand, register. In case of binary operations, the second operand can be a register or an immediate value. The result is always stored in the first operand.

``add rA, (rB|<value>)``

``dec rA``

``inc rA``

``mul rA, (rB|<value>)``

``sub rA, (rB|<value>)``


Bitwise operations
^^^^^^^^^^^^^^^^^^

All bitwise operations - with exception of ``not`` - take two operands: register and either register or immediate value. The result if always stored in the first operand.

``and rA, (rB|<value>)``

``not rA``

``or rA, (rB|<value>)``

``shiftl rA, (rB|<value>)``

``shiftr rA, (rB|<value>)``

``xor rA, (rB|<values>)``


Branching instructions
^^^^^^^^^^^^^^^^^^^^^^

Unconditional branching
"""""""""""""""""""""""

``j (rA|<value>)``

Conditional branching
"""""""""""""""""""""

All conditional branching instructions comes in form ``<inst> rA`` or ``<inst> <address>``. Depending on relevant flags, jump is performed to specified address.

+-------------+-------------------------+
| Instruction | Relevant flags          |
+-------------+-------------------------+
| ``be``      | ``e = 1``               |
| ``bne``     | ``e = 0``               |
| ``bs``      | ``s = 1``               |
| ``bns``     | ``s = 0``               |
| ``bz``      | ``z = 1``               |
| ``bnz``     | ``z = 0``               |
| ``bg``      | ``e = 0`` and ``s = 0`` |
| ``bge``     | ``e = 1`` or ``s = 0``  |
| ``bl``      | ``e = 0`` and ``s = 1`` |
| ``ble``     | ``e = 1`` or ``s = 1``  |
+-------------+-------------------------+

Comparing
"""""""""

Two instructions are available for comparing of values. Compare their operands and sets corresponding flags.

``cmp rA, (rB|<value>)``

``cmp rA, (rB|<value>)`` - treat operands as unsigned values


Port IO
^^^^^^^

All IO instructions take two operands: port number, specified by register or immediate value, and register.

``in (rA|<port>), rB`` - read 16-bit value from port and store it in ``rB``

``inb (rA|<port>), rB`` - read 8-bit value from port and store it in ``rB``

``out (rA|<port>), rB`` - write value from ``rB`` to port

``outb (rA|<port>), rB`` - write lower byte of ``rB`` to port


Interrupts
^^^^^^^^^^

Delivery
""""""""

If flag ``hwint`` is unset, no hardware IRQ can be accepted by CPU and stays queued. All queued IRQs will be delivered as soon as flag is set.

``cli`` - clear ``hwint`` flag

``sti`` - set ``hwint`` flag

In need of waiting for external events it is possible to suspend CPU until the next IRQ is delivered.

``idle`` - wait until next IRQ

Invocation
""""""""""

Only software interrupt routines can be invoked by means of special instruction. When invoked several events take place:

 - new stack page is allocated for interrupt routine ("interrupt stack")
 - all registers - except of ``r0`` - are stored on interrupt stack
 - privileged mode is enabled
 - ``ip``, ``cs`` and ``ds`` are set to values stored in interrupt vector table

When routine ends (via ``retint``) all these steps are undone, content of saved registers is restored, and possible return value can be found in ``r0``.

``int (rA|<index>)``

``retint`` - return from interrupt routine


Routines
^^^^^^^^

When routine is called, new stack frame is created. This step is undone when routines returns.

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

``rst`` - reset CPU state. All flags cleared, ``privileged = 1``, all registers set to ``0``

``mov rA, rB`` - copy value of ``rB`` into ``rA``

``swp rA, rB`` - swap content of two registers

``sis <value>`` - switch instruction set to a different one


Memory access
^^^^^^^^^^^^^

Address operand - ``{address}`` - can be specified in different ways:

 - ``rA`` - address is stored in register
 - ``rA[<offset>]`` - address is computed by addition of ``rA`` and ``offset``. ``offset`` can be both positive and negative. ``fp`` and ``sp`` can be also used as ``rA``.

Read
""""

``lw rA, {address}``

``lb rA, {address}`` - load 1 byte from memory

``li rA, <constant>`` - load ``constant`` into register

Write
"""""

``stw {address}, rA``

``stb {addres}, rA`` - store lower byte of ``rA``

Compare-and-swap
""""""""""""""""

``cas rA, rB, rC`` - read 16-bit value from address in register ``rA``. Compare it with value in register ``rB`` - if both are equal, take content of ``rC`` and store it in memory on address from ``rA``, else store memory value in ``rB``.
