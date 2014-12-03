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
  li r0, &message
  call &writesn
  li r0, 0
  int r0

outb:
  # > r0: port
  # > r1: byte
  outb r0, r1
  ret

writesn:
  # > r0: string address
  # ...
  #   r0: port
  #   r1: current byte
  #   r2: string ptr
  push r1
  push r2
  push r0
  pop r2
  li r0, 0x100
.__fn_writesn_loop:
  lb r1, r2
  bz &.__fn_writesn_write_nl
  call &outb
  inc r2
  j &.__fn_writesn_loop
.__fn_writesn_write_nl:
  ; \n
  li r1, 0xA
  call &outb
  # \r
  li r1, 0xD
  call &outb
  li r0, 0
  pop r2
  pop r1
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
$
```

Let's see some dump...

```
$ tools/objdump -i hello-world.bin -avv
 [INFO] Input file: examples/hello-world.bin 
 [INFO] 
 [INFO] === File header === 
 [INFO]   Magic:    0xDEAD 
 [INFO]   Version:  1 
 [INFO]   Sections: 4 
 [INFO] 
 [INFO] === Sections === 
 [INFO] 
 [INFO] Name     Type     Flags       Base        Items    Size  Offset 
 [INFO] -------  -------  ----------  --------  -------  ------  -------- 
 [INFO] .rodata  DATA     R-- (0x01)  0x000000        0       0  0x0000C6 
 [INFO] .data    DATA     RW- (0x03)  0x000100       14      14  0x0000C6 
 [INFO] .text    TEXT     R-X (0x05)  0x000200       24      96  0x0000D4 
 [INFO] .symtab  SYMBOLS  --- (0x00)  0x000400        4    1048  0x000134 
 [INFO] 
 [INFO] === Symbols === 
 [INFO] 
 [INFO] Name     Section    Address    Type        Size  Content 
 [INFO] -------  ---------  ---------  --------  ------  ---------------- 
 [INFO] message  .data      0x000100   string        14  "Hello, world!" 
 [INFO] main     .text      0x000200   function       0 
 [INFO] outb     .text      0x000210   function       0 
 [INFO] writesn  .text      0x000218   function       0 
 [INFO] 
 [INFO] === Disassemble == 
 [INFO] 
 [INFO]    Section .text 
 [INFO]    0x000200 li r0, 0x0100 
 [INFO]    0x000204 call 0x0010 
 [INFO]    0x000208 li r0, 0x0000 
 [INFO]    0x00020C int r0 
 [INFO]    0x000210 outb r0, r1 
 [INFO]    0x000214 ret 
 [INFO]    0x000218 push r1 
 [INFO]    0x00021C push r2 
 [INFO]    0x000220 push r0 
 [INFO]    0x000224 pop r2 
 [INFO]    0x000228 li r0, 0x0100 
 [INFO]    0x00022C lb r2, r1 
 [INFO]    0x000230 bz 0x000C 
 [INFO]    0x000234 call -0x0028 
 [INFO]    0x000238 inc r2 
 [INFO]    0x00023C j -0x0014 
 [INFO]    0x000240 li r1, 0x000A 
 [INFO]    0x000244 call -0x0038 
 [INFO]    0x000248 li r1, 0x000D 
 [INFO]    0x00024C call -0x0040 
 [INFO]    0x000250 li r0, 0x0000 
 [INFO]    0x000254 pop r2 
 [INFO]    0x000258 pop r1 
 [INFO]    0x00025C ret 
 [INFO] 
```
