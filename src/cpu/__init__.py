import Queue
import sys
import threading
import time

import instructions
import registers
import mm
import io
import irq

from mm import UInt8, UInt16

from registers import Registers
from instructions import Opcodes

from errors import CPUException, AccessViolationError, InvalidResourceError
from util import *

CPU_SLEEP_QUANTUM = 0.1

def log_cpu_core_state(core):
  cpuid_prefix = '#%i:#%i: ' % (core.cpu.id, core.id)

  for reg in range(0, Registers.REGISTER_SPECIAL):
    info(cpuid_prefix, 'reg%i=0x%X' % (reg, core.REG(reg).u16))

  info(cpuid_prefix, 'ip=0x%X' % core.IP().u16)
  info(cpuid_prefix, 'sp=0x%X' % core.SP().u16)
  info(cpuid_prefix, 'priv=%i, hwint=%i' % (core.FLAGS().privileged, core.FLAGS().hwint))
  info(cpuid_prefix, 'eq=%i, z=%i, o=%i' % (core.FLAGS().eq, core.FLAGS().z, core.FLAGS().o))
  info(cpuid_prefix, 'thread=%s, keep_running=%s' % (core.thread.name, core.keep_running))
  info(cpuid_prefix, 'exit_code=%i' % core.exit_code)

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.registers = registers.RegisterSet()

    self.keep_running = True
    self.thread = None
    self.idle = False

    self.__irq_queue = Queue.Queue()

    self.exit_code = 0

  def FLAGS(self):
    return self.registers.flags.flags

  def REG(self, reg):
    return self.registers[reg]

  def MEM_IN(self, addr):
    return self.memory.read_u16(addr)

  def MEM_OUT(self, addr, value):
    self.memory.write_u16(addr, value)

  def IP(self):
    return self.registers[Registers.IP]

  def SP(self):
    return self.registers[Registers.SP]

  def reset(self, new_ip = 0):
    for reg in registers.RESETABLE_REGISTERS:
      self.REG(reg).u16 = 0

    self.FLAGS().privileged = 0
    self.FLAGS().hwint = 1
    self.FLAGS().eq = 0
    self.FLAGS().z = 0
    self.FLAGS().o = 0

    self.IP().u16 = new_ip

  def __push(self, *regs):
    for reg in regs:
      self.SP().u16 -= 2
      self.MEM_OUT(self.SP().u16, self.REG(reg).u16)

  def __pop(self, *regs):
    for reg in regs:
      self.REG(reg).u16 = self.MEM_IN(self.SP().u16).u16
      self.SP().u16 += 2

  def __do_interupt(self, new_ip):
    self.__push(Registers.FLAGS)
    self.__push(Registers.IP)
    self.registers.ip.u16 = new_ip.u16
    self.privileged = 1

  def __do_int(self, index):
    self.__do_interrupt(self.memory.read_u16(self.memory.header.int_table_address + index * 2))

  def __do_irq(self, index):
    self.__do_interrupt(self.memory.read_u16(self.memory.header.irq_table_address + index * 2))
    self.idle = False

  def __do_retint(self):
    __check_protected_ins()
    self.__pop(Registers.IP, Registers.FLAGS)

  @property
  def privileged(self):
    return self.FLAGS().privileged

  @privileged.setter
  def privileged(self, value):
    self.FLAGS().privileged = value

  def step(self):
    # Check HW interrupt sources
    REG       = lambda reg: self.registers[reg]
    REGI1     = lambda: self.registers[ins.reg1]
    REGI2     = lambda: self.registers[ins.reg2]
    MEM_IN8   = lambda addr: self.memory.read_u8(addr)
    MEM_IN16  = lambda addr: self.memory.read_u16(addr)
    MEM_OUT8  = lambda addr, val: self.memory.write_u8(addr, value)
    MEM_OUT16 = lambda addr, val: self.memory.write_u16(addr, value)
    IP        = lambda: self.registers[Registers.IP]
    FLAGS     = lambda: self.registers.flags.flags

    def IP_IN():
      ret = MEM_IN16(IP().u16)

      debug('IP_IN: ip=0x%X, value=0x%X' % (IP().u16, ret.u16))

      IP().u16 += 2
      return ret

    # Read next instruction
    ins = instructions.InstructionBinaryFormat()
    ins.generic.ins = IP_IN().u16

    opcode = ins.nullary.opcode
    ins = getattr(ins, instructions.INSTRUCTIONS[opcode].binary_format)

    def __check_protected_ins():
      if not self.privileged:
        raise AccessViolationError('Instruction not allowed in unprivileged mode: opcode=%i' % opcode)

    def __check_protected_reg(reg):
      if reg in registers.PROTECTED_REGISTERS and not self.privileged:
        raise AccessViolationError('Access not allowed in unprivileged mode: opcode=%i reg=%i' % (opcode, reg))

    def __check_protected_port(port):
      if port.u16 not in self.cpu.ports:
        raise InvalidResourceError('Unhandled port: port=%i' % port)

      if self.cpu.ports[port.u16].is_protected and not self.privileged:
        raise AccessViolationError('Access to port not allowed in unprivileged mode: opcode=%i, port=%i' % (opcode, port))

    class AFLAGS_CTX(object):
      def __init__(self, dst):
        super(AFLAGS_CTX, self).__init__()

        self.dst = dst

      def __enter__(self):
        FLAGS().z = 0
        FLAGS().o = 0

      def __exit__(self, *args, **kwargs):
        if self.dst.u16 == 0:
          FLAGS().z = 1
        #if self.dst.u16 overflown:
        #  FLAGS().o = 1

        return False

    if   opcode == Opcodes.NOP:
      pass

    elif   opcode == Opcodes.INT:
      self.__do_int(REGI1().u16)

    elif opcode == Opcodes.RETINT:
      __check_protected_ins()

      self.__pop(Registers.IP, Registers.FLAGS)

    elif opcode == Opcodes.CLI:
      __check_protected_ins()

      FLAGS().hwint = 0

    elif opcode == Opcodes.STI:
      __check_protected_ins()

      FLAGS().hwint = 1

    elif opcode == Opcodes.HLT:
      __check_protected_ins()

      self.exit_code = REGI1().u16
      self.keep_running = False

      info('CPU #%i:%i halt!' % (self.cpu.id, self.id))
      log_cpu_core_state(self)

    elif opcode == Opcodes.PUSH:
      self.__push(ins.reg1)

    elif opcode == Opcodes.POP:
      __check_protected_reg(ins.reg1)

      self.__pop(ins.reg1)

    elif opcode == Opcodes.LOAD:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI2()):
        if ins.byte:
          REGI2().u16 = 0
          REGI2().u16 = MEM_IN8(REGI1().u16).u8
        else:
          REGI2().u16 = MEM_IN16((REGI1().u16)).u16

    elif opcode == Opcodes.STORE:
      if ins.byte:
        MEM_OUT8(REGI2().u16, REGI1().u16 & 0xFF)
      else:
        MEM_OUT16(REGI2().u16, REGI1().u16)

    elif opcode == Opcodes.INC:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 += 1

    elif opcode == Opcodes.DEC:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 -= 1

    elif opcode == Opcodes.ADD:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 += REGI2().u16

    elif opcode == Opcodes.SUB:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 -= REGI2().u16

    elif opcode == Opcodes.MUL:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 *= REGI2().u16

    elif opcode == Opcodes.DIV:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 /= REGI2().u16

    elif opcode == Opcodes.JMP:
      IP().u16 = IP_IN().u16

    elif opcode == Opcodes.JE:
      if FLAGS().eq:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().eq = 0

    elif opcode == Opcodes.JNE:
      if not FLAGS().eq:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().eq = 0

    elif opcode == Opcodes.CALL:
      new_ip = IP_IN().u16

      self.__push(Registers.IP)
      IP().u16 = new_ip

    elif opcode == Opcodes.RET:
      self.__pop(Registers.IP)

    elif opcode == Opcodes.IN:
      port = REGI1()

      __check_protected_port(port)
      __check_protected_reg(ins.reg2)

      if ins.byte:
        REGI2().u16 = 0
        REGI2().u16 = UInt16(self.cpu.ports[port.u16].read_u8(port).u8).u16
      else:
        REGI2().u16 = self.cpu.ports[port.u16].read_u16(port).u16

    elif opcode == Opcodes.OUT:
      port = REGI2()

      __check_protected_port(port)

      debug('OUT %u, %u' % (port.u16, REGI1().u16))

      if ins.byte:
        self.cpu.ports[port.u16].write_u8(port, UInt8(REGI1().u16))
      else:
        self.cpu.ports[port.u16].write_u16(port, REGI1())

    elif opcode == Opcodes.LOADA:
      __check_protected_reg(ins.reg1)

      value = IP_IN().u16

      debug('LOADA r%i, 0x%X' % (ins.reg1, value))

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 = value

    elif opcode == Opcodes.RST:
      __check_protected_ins()

      self.reset()

    elif opcode == Opcodes.CPUID:
      __check_protected_reg(ins.reg1)

      REGI1().u16 = UInt8(self.cpu.id).u8 << 8 | UInt8(self.id).u8

    elif opcode == Opcodes.IDLE:
      __check_protected_ins()

      self.idle = True

    elif opcode == Opcodes.JZ:
      if FLAGS().z:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().z = 0

    elif opcode == Opcodes.JNZ:
      if not FLAGS().z:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().z = 0

    elif opcode == Opcodes.AND:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 &= REGI2().u16

    elif opcode == Opcodes.OR:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 |= REGI2().u16

    elif opcode == Opcodes.XOR:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 ^= REGI2().u16
    
    elif opcode == Opcodes.NOT:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        REGI1().u16 = ~REGI1().u16

    else:
      raise CPUException('Unknown opcode: %i' % opcode)

  def loop(self):
    while self.keep_running:
      irq_source = None

      if self.idle:
        irq_source = self.__irq_queue.get(True)
      elif self.registers.flags.flags.hwint:
        try:
          irq_source = self.__irq_queue.get(False)
        except Queue.Empty:
          pass

      if irq_source:
        self.__do_irq(irq_source.irq)
        self.__irq_queue.task_done()

      try:
        self.step()
      except CPUException, e:
        error(str(e))
        log_cpu_core_state(self)
        self.keep_running = False

  def boot(self):
    self.thread = threading.Thread(target = self.loop, name = 'CPU #%i:#%i' % (self.cpu.id, self.id))
    info('CPU #%i:#%i boot!' % (self.cpu.id, self.id))
    log_cpu_core_state(self)
    self.thread.start()

class CPU(object):
  def __init__(self, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()
    self.__cores = [CPUCore(i, self, self.memory) for i in range(0, cores)]

    self.__irq_sources = irq.IRQSourceSet()
    self.ports = io.IOPortSet()

    self.keep_running = True
    self.thread = None

    self.exit_code = 0

  def register_irq_source(self, irq, src, reassign = False):
    if self.__irq_sources[irq]:
      if not reassign:
        raise InvalidResourceError('IRQ already assigned: %i' % irq)

      for i in range(0, len(self.__irq_sources)):
        if not self.__irq_sources[i]:
          irq = i
          break
      else:
        raise InvalidResourceError('IRQ already assigned, no available free IRQ: %i' % irq)

    self.__irq_sources[irq] = src
    return irq

  def unregister_irq_source(self, irq):
    self.__irq_sources[irq] = None

  def register_port(self, port, handler):
    if port in self.ports:
      raise IndexError('Port already assigned: %i' % port)

    self.ports[port] = handler

  def unregister_port(self, port):
    del self.ports[port]

  def loop(self):
    while self.keep_running:
      time.sleep(CPU_SLEEP_QUANTUM)

      for src in self.__irq_sources:
        if not src:
          continue
        if src.on_tick():
          for core in self.__cores:
            if core.idle:
              core.__irq_queue.put(src)
          else:
            self.__cores[0].__irq_queue.put(src)

      if len([core for core in self.__cores if core.thread.is_alive()]) == 0:
        info('CPU #%i halt!' % self.id)
        break

  def boot(self, privileged = False):
    mm_header = self.memory.header

    for core in self.__cores:
      core.reset(new_ip = self.memory.read_u16(mm_header.boot_ip_map_address + core.id * 2, privileged = True).u16)

    if privileged:
      self.__cores[0].privileged = 1

    for core in self.__cores:
      core.boot()

    self.thread = threading.Thread(target = self.loop, name = 'CPU #%i' % self.id)
    self.thread.start()

