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

SERVICE_ROUTINES = {
  'halt': [
    '  loada r0, 0',
    '  hlt r0'
  ],
  'idle_loop': [
    'main:',
    '  idle',
    '  jmp main'
  ]
}

def get_service_routine(routine_name, csb, dsb):
  if routine_name not in SERVICE_ROUTINES:
    raise CPUException('Unknown service routine requested: "%s"' % routine_name)

  import cpu.compile
  buff = SERVICE_ROUTINES[routine_name]
  (csb, cs), (dsb, ds), symbols = cpu.compile.compile_buffer(buff, csb = csb, dsb = dsb)

  return (csb, cs, dsb, ds)

def log_cpu_core_state(core, logger = None):
  logger = logger or debug

  cpuid_prefix = '#%i:#%i: ' % (core.cpu.id, core.id)

  for reg in range(0, Registers.REGISTER_SPECIAL):
    logger(cpuid_prefix, 'reg%i=0x%X' % (reg, core.REG(reg).u16))

  logger(cpuid_prefix, 'cs=0x%X' % core.CS().u16)
  logger(cpuid_prefix, 'ds=0x%X' % core.DS().u16)
  logger(cpuid_prefix, 'ip=0x%X' % core.IP().u16)
  logger(cpuid_prefix, 'sp=0x%X' % core.SP().u16)
  logger(cpuid_prefix, 'priv=%i, hwint=%i' % (core.FLAGS().privileged, core.FLAGS().hwint))
  logger(cpuid_prefix, 'eq=%i, z=%i, o=%i' % (core.FLAGS().eq, core.FLAGS().z, core.FLAGS().o))
  logger(cpuid_prefix, 'thread=%s, keep_running=%s' % (core.thread.name, core.keep_running))
  logger(cpuid_prefix, 'exit_code=%i' % core.exit_code)

  if core.current_instruction:
    ins, additional_operands = instructions.disassemble_instruction(core.current_instruction, core.memory.read_u16(core.CS().u16 + core.IP().u16, privileged = True))
    logger(cpuid_prefix, 'current=%s' % ins)
  else:
    logger(cpuid_prefix, 'current=')

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.registers = registers.RegisterSet()

    self.current_instruction = None

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
    return self.registers.ip

  def SP(self):
    return self.registers.sp

  def CS(self):
    return self.registers.cs

  def DS(self):
    return self.registers.ds

  def reset(self, new_ip = 0):
    for reg in registers.RESETABLE_REGISTERS:
      self.REG(reg).u16 = 0

    self.FLAGS().privileged = 0
    self.FLAGS().hwint = 1
    self.FLAGS().eq = 0
    self.FLAGS().z = 0
    self.FLAGS().o = 0
    self.FLAGS().s = 0

    self.IP().u16 = new_ip

  def __push(self, *regs):
    for reg in regs:
      self.SP().u16 -= 2

      debug('__push: save %s (0x%04X) to 0x%04X' % (reg, self.REG(reg).u16, self.SP().u16))

      self.MEM_OUT(self.SP().u16, self.REG(reg).u16)

  def __pop(self, *regs):
    for reg in regs:
      self.REG(reg).u16 = self.MEM_IN(self.SP().u16).u16
      debug('__pop: load %s (0x%04X) from 0x%04X' % (reg, self.REG(reg).u16, self.SP().u16))
      self.SP().u16 += 2

  def __do_interupt(self, new_ip):
    self.__push(Registers.FLAGS, Registers.IP, Registers.DS, Registers.CS)
    self.registers.ip.u16 = new_ip.u16
    self.privileged = 1

  def __do_int(self, index):
    self.__do_interrupt(self.memory.read_u16(self.memory.header.int_table_address + index * 2))

  def __do_irq(self, index):
    self.__do_interrupt(self.memory.read_u16(self.memory.header.irq_table_address + index * 2))
    self.idle = False

  def __do_retint(self):
    __check_protected_ins()
    self.__pop(Registers.CS, Registers.DS, Registers.IP, Registers.FLAGS)

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
    IP        = lambda: self.registers.ip
    FLAGS     = lambda: self.registers.flags.flags
    CS        = lambda: self.registers.cs
    DS        = lambda: self.registers.ds

    CS_ADDR = lambda addr: addr
    DS_ADDR = lambda addr: addr

    #CS_ADDR = lambda addr: (CS().u16 & 0xFF) | addr
    #DS_ADDR = lambda addr: (DS().u16 & 0xFF) | addr

    def IP_IN():
      addr = CS_ADDR(IP().u16)
      ret = MEM_IN16(addr)

      debug('IP_IN: cs=0x%X, ip=0x%X, addr=0x%X, value=0x%X' % (CS().u16, IP().u16, addr, ret.u16))

      IP().u16 += 2
      return ret

    saved_IP = IP().u16

    # Read next instruction
    ins = instructions.InstructionBinaryFormat()
    ins.generic.ins = IP_IN().u16

    opcode = ins.nullary.opcode
    ins = getattr(ins, instructions.INSTRUCTIONS[opcode].binary_format)

    self.current_instruction = ins

    def __check_protected_ins():
      if not self.privileged:
        raise AccessViolationError('Instruction not allowed in unprivileged mode: opcode=%i' % opcode)

    def __check_protected_reg(reg):
      if reg in registers.PROTECTED_REGISTERS and not self.privileged:
        raise AccessViolationError('Access not allowed in unprivileged mode: opcode=%i reg=%i' % (opcode, reg))

    def __check_protected_port(port):
      if port.u16 not in self.cpu.machine.ports:
        raise InvalidResourceError('Unhandled port: port=%u' % port.u16)

      if self.cpu.machine.ports[port.u16].is_protected and not self.privileged:
        raise AccessViolationError('Access to port not allowed in unprivileged mode: opcode=%i, port=%u' % (opcode, port))

    class AFLAGS_CTX(object):
      def __init__(self, dst):
        super(AFLAGS_CTX, self).__init__()

        self.dst = dst

      def __enter__(self):
        FLAGS().z = 0
        FLAGS().o = 0
        FLAGS().s = 0

      def __exit__(self, *args, **kwargs):
        if self.dst.u16 == 0:
          FLAGS().z = 1
        #if self.dst.u16 overflown:
        #  FLAGS().o = 1

        return False

    disassemble_next_cell = self.memory.read_u16(CS_ADDR(IP().u16), privileged = True)
    info('0x%04X: %s' % (saved_IP, instructions.disassemble_instruction(self.current_instruction, disassemble_next_cell)[0]))
    log_cpu_core_state(self)

    if   opcode == Opcodes.NOP:
      pass

    elif   opcode == Opcodes.INT:
      self.__do_int(REGI1().u16)

    elif opcode == Opcodes.RETINT:
      __check_protected_ins()

      self.__do_retint()

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

      info('Core #%i:%i halt!' % (self.cpu.id, self.id))
      log_cpu_core_state(self)

    elif opcode == Opcodes.PUSH:
      self.__push(ins.reg1)

    elif opcode == Opcodes.POP:
      __check_protected_reg(ins.reg1)

      self.__pop(ins.reg1)

    elif opcode == Opcodes.LOAD:
      __check_protected_reg(ins.reg1)

      with AFLAGS_CTX(REGI1()):
        addr = DS_ADDR(REGI2().u16)

        if ins.byte:
          REGI1().u16 = 0
          REGI1().u16 = MEM_IN8(addr).u8
        else:
          REGI1().u16 = MEM_IN16(addr).u16

    elif opcode == Opcodes.STORE:
      addr = DS_ADDR(REGI2().u16)

      if ins.byte:
        MEM_OUT8(addr, REGI1().u16 & 0xFF)
      else:
        MEM_OUT16(addr, REGI1().u16)

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
        REGI2().u16 = UInt16(self.cpu.machine.ports[port.u16].read_u8(port).u8).u16
      else:
        REGI2().u16 = self.cpu.machine.ports[port.u16].read_u16(port).u16

    elif opcode == Opcodes.OUT:
      port = REGI1()

      __check_protected_port(port)

      if ins.byte:
        self.cpu.machine.ports[port.u16].write_u8(port, UInt8(REGI2().u16))
      else:
        self.cpu.machine.ports[port.u16].write_u16(port, REGI2())

    elif opcode == Opcodes.LOADA:
      __check_protected_reg(ins.reg1)

      value = IP_IN().u16

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

    elif opcode == Opcodes.CMP:
      FLAGS().eq = 0
      FLAGS().s = 0

      if   REGI1().u16 == REGI2().u16:
        FLAGS().eq = 1

      elif REGI1().u16  < REGI2().u16:
        FLAGS().s = 1

      elif REGI1().u16  > REG2().u16:
        pass

    elif opcode == Opcodes.JS:
      if FLAGS().s:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().s = 0

    elif opcode == Opcodes.JNS:
      if not FLAGS().s:
        IP().u16 = IP_IN().u16
      else:
        IP().u16 += 2

      FLAGS().s = 0

    else:
      raise CPUException('Unknown opcode: %i' % opcode)

    debug('Opcode exit: %s' % opcode)

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

  def boot(self, init_state):
    csr, csb, dsr, dsb, sp, privileged = init_state

    self.REG(Registers.CS).u16 = csr.u16
    self.REG(Registers.DS).u16 = dsr.u16
    self.REG(Registers.IP).u16 = csb.u16
    self.REG(Registers.SP).u16 = sp.u16
    self.FLAGS().privileged = 1 if privileged else 0

    self.thread = threading.Thread(target = self.loop, name = 'Core #%i:#%i' % (self.cpu.id, self.id))
    info('Core #%i:#%i boot!' % (self.cpu.id, self.id))
    log_cpu_core_state(self)
    self.thread.start()

class CPU(object):
  def __init__(self, machine, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()
    self.cores = [CPUCore(i, self, self.memory) for i in range(0, cores)]

    self.keep_running = True
    self.thread = None

    self.exit_code = 0

  def loop(self):
    while self.keep_running:
      time.sleep(CPU_SLEEP_QUANTUM * 10)

      if len([core for core in self.cores if core.thread.is_alive()]) == 0:
        info('CPU #%i halt!' % self.id)
        break

  def boot(self, init_states, bsp = False):
    mm_header = self.memory.header

    for core in self.cores:
      core.boot(init_states.pop(0))

    self.thread = threading.Thread(target = self.loop, name = 'CPU #%i' % self.id)
    self.thread.start()

