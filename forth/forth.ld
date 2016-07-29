#!/usr/bin/env python

(
    0x00000000,
  ( '.text',      [ r'\.text'                    ]),
  ( '.bootstack', [ r'\.bootstack'               ]),
  ( '.rodata',    [ r'\.rodata', r'\.rodata\..*', r'\.data\..*\.ro' ]),
  ( '.data',      [ r'\.data',   r'\.data\..*'   ]),
  ( '.bss',       [ r'\.bss'                     ]),

    0x00009000,
  ( '.userspace', [ r'\.userspace'               ])
)
