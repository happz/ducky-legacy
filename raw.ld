#!/usr/bin/env python

(
    0x00000000,
  ( '.text',      [ r'\.text'                    ]),
  ( '.rodata',    [ r'\.rodata', r'\.rodata\..*' ]),
  ( '.data',      [ r'\.data',   r'\.data\..*'   ])
)
