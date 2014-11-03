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
  li r1, &message
  calli @writesn
  hlt r0

outb:
  # > r1: port
  # > r2: byte
  outb r1, r2 b
  ret

writesn:
  # > r1: string address
  #   r2: current byte
  #   r3: port
  push r2
  push r3
  li r3, 0x100
__fn_writesn_loop:
  lb r2, r1
  bz @__fn_writesn_write_nl
  push r1
  mov r1, r3
  calli @outb
  pop r1
  inc r1
  j @__fn_writesn_loop
__fn_writesn_write_nl:
  push r1
  li r1, 0x100
  # \n
  li r2, 0xA
  calli @outb
  # \r
  li r2, 0xD
  calli @outb
  pop r1
  li r0, 0
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
 [INFO] Input file: hello-world.bin 
 [INFO] 
 [INFO] === File header === 
 [INFO]   Magic:    0xDEAD 
 [INFO]   Version:  1 
 [INFO]   Sections: 3 
 [INFO] 
 [INFO] === Sections === 
 [INFO] 
 [INFO] * Section #0 
 [INFO]   Name:   .text 
 [INFO]   Type:   TEXT 
 [INFO]   Flags:  R-X (0x5) 
 [INFO]   Base:   0x000000 
 [INFO]   Size:   27 
 [INFO]   Offset: 0x00008A 
 [INFO] 
 [INFO]    0x000000 li r1, 0x0100 
 [INFO]    0x000004 calli 0x000014 
 [INFO]    0x000008 hlt r0 
 [INFO]    0x00000C outb r1, r2 
 [INFO]    0x000010 ret 
 [INFO]    0x000014 push r2 
 [INFO]    0x000018 push r3 
 [INFO]    0x00001C li r3, 0x0100 
 [INFO]    0x000020 lb r2, r1 
 [INFO]    0x000024 bz 0x000040 
 [INFO]    0x000028 push r1 
 [INFO]    0x00002C mov r1, r3 
 [INFO]    0x000030 calli 0x00000C 
 [INFO]    0x000034 pop r1 
 [INFO]    0x000038 inc r1 
 [INFO]    0x00003C j 0x000020 
 [INFO]    0x000040 push r1 
 [INFO]    0x000044 li r1, 0x0100 
 [INFO]    0x000048 li r2, 0x000A 
 [INFO]    0x00004C calli 0x00000C 
 [INFO]    0x000050 li r2, 0x000D 
 [INFO]    0x000054 calli 0x00000C 
 [INFO]    0x000058 pop r1 
 [INFO]    0x00005C li r0, 0x0000 
 [INFO]    0x000060 pop r3 
 [INFO]    0x000064 pop r2 
 [INFO]    0x000068 ret 
 [INFO] 
 [INFO] * Section #1 
 [INFO]   Name:   .data 
 [INFO]   Type:   DATA 
 [INFO]   Flags:  RW- (0x3) 
 [INFO]   Base:   0x000100 
 [INFO]   Size:   14 
 [INFO]   Offset: 0x0000F6 
 [INFO] 
 [INFO] * Section #2 
 [INFO]   Name:   .symtab 
 [INFO]   Type:   SYMBOLS 
 [INFO]   Flags:  --- (0x0) 
 [INFO]   Base:   0x000000 
 [INFO]   Size:   4 
 [INFO]   Offset: 0x000104 
 [INFO] 
 [INFO]    Name:    message 
 [INFO]    Address: 0x000100 
 [INFO]    Size:    14 
 [INFO]    Section: 1 
 [INFO]    Type:    string 
 [INFO]    Content: "Hello, world!" 
 [INFO]    
 [INFO]    Name:    main 
 [INFO]    Address: 0x000000 
 [INFO]    Size:    0 
 [INFO]    Section: 0 
 [INFO]    Type:    function 
 [INFO]    
 [INFO]    Name:    outb 
 [INFO]    Address: 0x00000C 
 [INFO]    Size:    0 
 [INFO]    Section: 0 
 [INFO]    Type:    function 
 [INFO]    
 [INFO]    Name:    writesn 
 [INFO]    Address: 0x000014 
 [INFO]    Size:    0 
 [INFO]    Section: 0 
 [INFO]    Type:    function 
 [INFO]    
```
