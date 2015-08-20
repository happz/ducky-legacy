Virtual software
================


Calling convention
------------------

I use very simple calling convention in my code:

 - all arguments are in registers
 - first argument in ``r0``, second in ``r1``, ... You get the picture.
 - if there's too many arguments, refactor your code or use a stack...
 - return value is in ``r0``
 - callee is reponsible for save/restore of registers it's using, with exception of:
   - registers that were used for passing arguments - these are expected to have undefined value when callee returns
   - ``r0`` if callee returns value back to caller

All virtual interrupt routines, assembler code, any pieces of software I've written for this virtual machine follows this calling convention - unless stated otherwise...


Software interrupts
-------------------

Software interrupts provide access to library of common functions, and - in case of virtual interrupts - to internal, complex and otherwise inaccessible rouces of virtual machine itself.

For the list for existing software interrupts and their numbers, see :py:class:`ducky.irq.InterruptList`. However, by the nature of invoking a software interrupt, this list is not carved into a stone. You may easily provide your own ``IVT``, with entries leading to your own routines, and use e.g. the first entry, ``HALT``, to sing a song.

All values are defined in ``defs.asm`` file which you can include into your assembler sources.


``HALT``
^^^^^^^^

+---------------+--------------------+
| ``IVT`` entry | ``0``              |
+---------------+--------------------+
| Parameters    | ``r0`` - exit code |
+---------------+--------------------+

Halt a CPU core. Value in ``r0`` is propagated as a core's exit code. This interrupt never returns back to the caller.


``BLOCKIO``
^^^^^^^^^^^

+---------------+--------------------------------------------------------------------------+
| ``IVT`` entry | ``1``                                                                    |
+---------------+--------+--------------------+--------------------------------------------+
|               |        | Read mode          | Write mode                                 |
+---------------+--------+--------------------+--------------------------------------------+
| Parameters    | ``r0`` |  device id                                                      |
|               +--------+--------------------+--------------------------------------------+
|               | ``r1`` | bit #0: ``0`` for read, ``1`` for write                         |
|               |        | bit #1: ``0`` for synchronous, ``1`` for asynchronous operation |
|               +--------+--------------------+--------------------------------------------+
|               | ``r2`` | block id           | src memory address                         |
|               +--------+--------------------+--------------------------------------------+
|               | ``r3`` | dst memory address | block id                                   |
|               +--------+--------------------+--------------------------------------------+
|               | ``r4`` | number of blocks                                                |
+---------------+--------+-----------------------------------------------------------------+
| Returns       | ``r0`` | ``0`` for success                                               |
+---------------+--------+-----------------------------------------------------------------+


Perform block IO operation - transfer block between memory and storage device. Use the lowest bit of ``r1`` to specify direction:

 - ``0`` - `read mode`, blocks are transfered from storage into memory
 - ``1`` - `write mode`, blocks are tranfered from memory to storage

Current data segment is used for addressing memory locations.

If everything went fine, ``0`` is returned, any other value means error happened.

IO operation is a blocking action, interrupt will return back to the caller once the IO is finished. Non-blocking (`DMA`-like) mode is planned but not yet implemented.

This operation is implemented as a virtual interrupt, see :py:class:`ducky.blockio.BlockIOInterrupt` for details.


``VMDEBUG``
^^^^^^^^^^^

+---------------+----------------------------------------------------------------+
| ``IVT`` entry | ``2``                                                          |
+---------------+--------+-------------------------------------------------------+
|               |        | ``QUIET`` mode                                        |
+---------------+--------+-------------------------------------------------------+
| Parameters    | ``r0`` | ``0``                                                 |
|               +--------+-------------------------------------------------------+
|               | ``r1`` | ``0`` for `quiet` mode, anything else for `full` mode |
+---------------+--------+-------------------------------------------------------+
| Returns       | ``r0`` | ``0`` for success                                     |
+---------------+--------+-------------------------------------------------------+

``VM`` interrupt allows control of VM debugging output. Currently, only two levels of verbosity that are available are `quiet` and `full` mode. In `quiet` mode, VM produces no logging output at all.

This interrupt can control level amount of debugging output in case when developer is interested only in debugging only a specific part of his code. Run VM with debugging turned on (``-d`` option), turn the debugging off at the beggining of the code, and turn it on again at the beggining of the interesting part to get detailed output.


``MM``
^^^^^^

+---------------+-----------------------------------------+
| ``IVT`` entry | ``4``                                   |
+---------------+--------+----------------+---------------+
|               |        | ``mtell``      | ``mprotect``  |
+---------------+--------+----------------+---------------+
| Parameters    | ``r0`` |  ``2``         | ``1``         |
|               +--------+----------------+---------------+
|               | ``r1`` | start address  | start address |
|               +--------+----------------+---------------+
|               | ``r2`` | end address    | end address   |
|               +--------+----------------+---------------+
|               | ``r3`` | flags          | flags         |
+---------------+--------+----------------+---------------+
| Returns       | ``r0`` | ``0`` for success              |
+---------------+--------+--------------------------------+

``MM`` interrupt provides access to many memory-related operations, usually manipulating areas of the main memory. Specific operation is requested by setting proper value of ``r0``. See :py:class:`ducky.mm.interrupt.MMInterrupt` for more implementation details.

In general, operation is selected, and other parameters usually specify memory area by stating address of the first byte and the address of the first byte *laying after this area*. Return values are stored in ``r0``, if any.

Several flags can be used in invocations, see :py:class:`ducky.mm.interrupt.MMInterrupt` for their list.


``mtell``
"""""""""

Returns current flags set for memory area. Only ``MM_FLAG_CS`` is valid for this call.

When ``MM_FLAG_CS`` is set, addresses are resolved using current code segment, data segment is used otherwise.


``mprotect``
""""""""""""

Replace flags of the memory area by new ones.

When ``MM_FLAG_CS`` is set, addresses are resolved using current code segment, data segment is used otherwise.
