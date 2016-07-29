.. _glossary:

Glossary
========

.. glossary::

  binary
    Binary is the final piece in the process

  bootloader
    `Bootloader`, for purposes of this documentation, means virtually any piece
    of bytecode. It gains its "bootloader-like" property by the fact that it's
    the first piece of code that's executed by CPU core.

  EVT
    :ref:`EVT`

  HDT
    :ref:`HDT`

  linker
    `Linker` takes an :term:`object file` (or more, or even an archive), and
    creates a :term:`binary` by merging relevant sections and by replacing
    symbolic references with final offsets.

    :ref:`ducky-ld` provides this functionality.

  machine
    For a long time, Ducky existed only as an software simulator. But, since I
    got that great idea about getting me a simple FPGA and learn VHDL, this may
    no longer be true. So, when I write about `machine`, I mean both software
    simulator (:term:`VM`) *and* hardware materialization of Ducky SoC.

  object file
    `Object file` is a file containing compiled code in a form of distinct
    sections of instructions, data and other necessary resources. Despite
    sharing their format with :term:`binary` file, object files are usualy
    *not* executable because pretty much no instructions that address memory
    contain correct offsets, and refer to the locations using symbols. Final
    offsets are calculated and fixed by a :term:`linker`.

  VM
    `Virtual Machine`. For a long time, the only existing Ducky implementation.
