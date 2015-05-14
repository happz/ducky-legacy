Instruction set
===============

CPU supports multiple instruction set. The main one, `ducky`, is the main workhorse, suited for general coding, but other instruction sets can exist, e.g. coprocessor may use its own instruction set for its operations.

.. toctree::
  :maxdepth: 2

  ducky_instruction_set.rst
  math_copro_instruction_set.rst


Design principles
-----------------

 - load and store operations are performed by dedicated instructions
 - all memory-register transfers work with 16-bit operands, 8-bit operands are handled by special instructions when necessary
 - all memory-register transfers work with addresses that are aligned to the size of their operands - 2 bytes for 16-bit operands, 1 byte (so no alignment at all) for 8-bit operands
 - in most cases, destination operand is the first one. Exceptions are instructions that work with IO ports.
 - when content of a register is changed by instruction, several flags can be modified subsequently. E.g. when new value of register is zero, ``z`` flag is set.

Notes on documentation
^^^^^^^^^^^^^^^^^^^^^^

 - ``rN`` refers to generaly any register, from ``r0`` up to ``r12`` - special registers are refered to by their common names (e.g. ``SP``).
 - ``rA``, ``rB`` refer to the first and the second instruction operand respectively and stand for any register.
 - ``<value>`` means immediate, absolute value. This covers both integers, specified as base 10 or base 16 integers, both positive and negative, and labels and addresses, specified as ``&label``
 - when instruction accepts more than one operand type, it is documented using ``|`` character, e.g. ``(rA|<value>)`` means either register or immediate value
