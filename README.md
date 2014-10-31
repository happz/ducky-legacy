ducky
=====

Simple virtual CPU/machine

- - -

# Features

* wanna-be RISC instruction set, based on LOAD/STORE architecture, with fixed instruction width
* modular software and hardware interrupt sources and handlers
* user/privileged mode
* flat, paged memory model with RWX access control
* ELF-inspired bytecode files
* as, objdump and vm tools included

# Planned features

* console and timer irq sources
  * important pieces already finished, test & fix
* easy and simple way how to create/modify/load interrupt routines
* SMP and multi-core support
  * important pieces already finished
  * thread isolation
  * not tested yet
* virtual memory
  * page tables done
  * access control done
  * mmap'ed external sources not finished yet
* debugging support
* relocation support
* C compiler
* dynamic load/unload of bytecode
* external file I/O support

# Example

Let's use "Hello, world!" example - short code that prints quite unusual message:

```
$ cat examples/hello-world.asm
  .type message, string
  .string "Hello, world!"

main:
  loada r1, &message
  calli __fn_writesn_prolog
  hlt r0

__outb_prolog:
  # > r1: port
  # > r2: byte
  out r1, r2 b
  ret

__fn_writesn_prolog:
  # > r1: string address
  #   r2: current byte
  #   r3: port
  push r2
  push r3
  loada r3, 0x100
__fn_writesn_loop:
  load r2, r1 b
  jz __fn_writesn_write_nl
  push r1
  mov r1, r3
  calli __outb_prolog
  pop r1
  inc r1
  jmp __fn_writesn_loop
__fn_writesn_write_nl:
  push r1
  loada r1, 0x100
  # \n
  loada r2, 0xA b
  call __outb_prolog
  # \r
  loada r2, 0xD b
  call __outb_prolog
  pop r1
  loada r0, 0
  pop r3
  pop r2
  ret
```

Translate it into bytecode:

```
$ tools/as -f -i examples/hello-world.asm -o hello-world.bin
```

And fire a virtual machine:

```
$ tools/vm -b hello-world.bin          
Hello, world!
 [ERRR] Instruction not allowed in unprivileged mode: opcode=18 
$
```

Don't mind the error message - the last instruction is ```hlt```, which is not allowed in non-privileged mode. Which is the default mode from the start of common binaries.

Let's see some dump...

```
$ tools/objdump -i hello-world.bin -vvv -d
 [INFO] 
 [INFO] === File header === 
 [INFO]   Magic:    0xDEAD 
 [INFO]   Version:  1 
 [INFO]   Sections: 4 
 [INFO] 
 [INFO] === Sections === 
 [INFO] 
 [INFO] * Section #0 
 [INFO]   Type:   TEXT 
 [INFO]   Flags:  0x0 
 [INFO]   Base:   0x000000 
 [INFO]   Size:   57 
 [INFO]   Offset: 0x000036 
 [INFO] 
 [INFO]    0x000000 calli 0x0000A8 
 [INFO]    0x000004 hlt r0 
 [INFO]    0x000008 outb r1, r2 
 [INFO]    0x00000C ret 
 [INFO]    0x000010 push r4 
 [INFO]    0x000014 push r5 
 [INFO]    0x000018 li r5, 0x0100 
 [INFO]    0x00001C li r4, 0x0000 
 [INFO]    0x000020 cmp r4, r3 
 [INFO]    0x000024 be 0x000064 
 [INFO]    0x000028 bns 0x000064 
 [INFO]    0x00002C push r6 
 [INFO]    0x000030 mov r6, r4 
 [INFO]    0x000034 add r6, r2 
 [INFO]    0x000038 lb r6, r6 
 [INFO]    0x00003C push r1 
 [INFO]    0x000040 mov r1, r5 
 [INFO]    0x000044 push r2 
 [INFO]    0x000048 mov r2, r6 
 [INFO]    0x00004C calli 0x000008 
 [INFO]    0x000050 pop r2 
 [INFO]    0x000054 pop r1 
 [INFO]    0x000058 pop r6 
 [INFO]    0x00005C inc r4 
 [INFO]    0x000060 j 0x000020 
 [INFO]    0x000064 push r1 
 [INFO]    0x000068 mov r1, r5 
 [INFO]    0x00006C push r2 
 [INFO]    0x000070 li r2, 0x000A 
 [INFO]    0x000074 calli 0x000008 
 [INFO]    0x000078 pop r2 
 [INFO]    0x00007C pop r1 
 [INFO]    0x000080 push r1 
 [INFO]    0x000084 mov r1, r5 
 [INFO]    0x000088 push r2 
 [INFO]    0x00008C li r2, 0x000D 
 [INFO]    0x000090 calli 0x000008 
 [INFO]    0x000094 pop r2 
 [INFO]    0x000098 pop r1 
 [INFO]    0x00009C pop r5 
 [INFO]    0x0000A0 pop r4 
 [INFO]    0x0000A4 ret 
 [INFO]    0x0000A8 push r3 
 [INFO]    0x0000AC li r3, 0x0100 
 [INFO]    0x0000B0 push r1 
 [INFO]    0x0000B4 li r1, 0x0000 
 [INFO]    0x0000B8 push r2 
 [INFO]    0x0000BC mov r2, r3 
 [INFO]    0x0000C0 push r3 
 [INFO]    0x0000C4 li r3, 0x000D 
 [INFO]    0x0000C8 calli 0x000010 
 [INFO]    0x0000CC pop r3 
 [INFO]    0x0000D0 pop r2 
 [INFO]    0x0000D4 pop r1 
 [INFO]    0x0000D8 pop r3 
 [INFO]    0x0000DC li r0, 0x0000 
 [INFO]    0x0000E0 ret 
 [INFO] 
 [INFO] * Section #1 
 [INFO]   Type:   DATA 
 [INFO]   Flags:  0x0 
 [INFO]   Base:   0x000100 
 [INFO]   Size:   14 
 [INFO]   Offset: 0x00011A 
 [INFO] 
 [INFO] * Section #2 
 [INFO]   Type:   STACK 
 [INFO]   Flags:  0x0 
 [INFO]   Base:   0x000000 
 [INFO]   Size:   0 
 [INFO]   Offset: 0x000000 
 [INFO] 
 [INFO] * Section #3 
 [INFO]   Type:   SYMBOLS 
 [INFO]   Flags:  0x0 
 [INFO]   Base:   0x000000 
 [INFO]   Size:   1 
 [INFO]   Offset: 0x000128 
 [INFO] 
 [INFO]    Name:    some_data 
 [INFO]    Address: 0x000100 
 [INFO]    Size:    14 
 [INFO]    Section: 1 
 [INFO]    Type:    string 
 [INFO]    Content: "Hello, world!" 
 [INFO]
```
