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

Lets use "Hello, world!" example - short code that prints quite unusual message:

```
$ cat examples/hello-world.asm
data message, "Hello, world!"
main:
  loada r1, 14
  loada r2, &message
  loada r3, 0x100
loop:
  load r2, r4 b
  out r4, r3 b
  inc r2
  dec r1
  jnz loop
  loada r2, 10
  out r2, r3 b
  loada r2, 13
  out r2, r3 b
  loada r1, 0
  hlt r1
```

Translate it into bytecode:

```
$ tools/as -vvv -f -i examples/hello-world.asm -o hello-world.bin
 [INFO] Input file: examples/hello-world.asm
 [INFO] Bytecode translation completed
 [INFO] Output file: hello-world.bin
 [INFO] Source file successfully translated and saved
```

And fire a virtual machine:

```
$ tools/vm -vvv -b hello-world.bin
 [INFO] CPU #0:0 boot!
 [INFO] #0:#0:  reg0=0x0
 [INFO] #0:#0:  reg1=0x0
 [INFO] #0:#0:  reg2=0x0
 [INFO] #0:#0:  reg3=0x0
 [INFO] #0:#0:  reg4=0x0
 [INFO] #0:#0:  reg5=0x0
 [INFO] #0:#0:  reg6=0x0
 [INFO] #0:#0:  reg7=0x0
 [INFO] #0:#0:  reg8=0x0
 [INFO] #0:#0:  reg9=0x0
 [INFO] #0:#0:  reg10=0x0
 [INFO] #0:#0:  reg11=0x0
 [INFO] #0:#0:  reg12=0x0
 [INFO] #0:#0:  ip=0x500
 [INFO] #0:#0:  sp=0x0
 [INFO] #0:#0:  priv=1, hwint=1
 [INFO] #0:#0:  eq=0, z=0, o=0
 [INFO] #0:#0:  thread=CPU #0:#0, keep_running=True
 [INFO] #0:#0:  exit_code=0
Hello, world!
 [INFO] CPU #0:0 halt!
 [INFO] #0:#0:  reg0=0x0
 [INFO] #0:#0:  reg1=0x0
 [INFO] #0:#0:  reg2=0xD
 [INFO] #0:#0:  reg3=0x100
 [INFO] #0:#0:  reg4=0x0
 [INFO] #0:#0:  reg5=0x0
 [INFO] #0:#0:  reg6=0x0
 [INFO] #0:#0:  reg7=0x0
 [INFO] #0:#0:  reg8=0x0
 [INFO] #0:#0:  reg9=0x0
 [INFO] #0:#0:  reg10=0x0
 [INFO] #0:#0:  reg11=0x0
 [INFO] #0:#0:  reg12=0x0
 [INFO] #0:#0:  ip=0x52A
 [INFO] #0:#0:  sp=0x0
 [INFO] #0:#0:  priv=1, hwint=1
 [INFO] #0:#0:  eq=0, z=1, o=0
 [INFO] #0:#0:  thread=CPU #0:#0, keep_running=False
 [INFO] #0:#0:  exit_code=0
 [INFO] CPU #0 halt!
 [INFO] All halted
```

Don't mind debug messages, focus on sweet and nice like in the middle. Oh this is good! :)
