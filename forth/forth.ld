#!/usr/bin/env python

(
    0x00000000,
  ( '.text.boot', [ r'\.text\.boot'              ]),

    # see TEXT_BASE in ducky-forth-defs.s
    0x00000A00,
  ( '.text',      [ r'\.text'                    ]),
  ( '.bootstack', [ r'\.bootstack'               ]),
  ( '.rodata',    [ r'\.rodata', r'\.rodata\..*', r'\.data\..*\.ro' ]),
  ( '.data',      [ r'\.data',   r'\.data\..*'   ]),
  ( '.bss',       [ r'\.bss'                     ]),

    0x0000A000,
  ( '.userspace', [ r'\.userspace'               ])
)
