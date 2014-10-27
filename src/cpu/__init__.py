import Queue
import sys
import threading
import time

import instructions
import registers
import mm
import io
import irq

from mm import UInt8, UInt16, UInt24
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT
from mm import segment_addr_to_addr

from registers import Registers
from instructions import Opcodes

from errors import CPUException, AccessViolationError, InvalidResourceError
from util import *

from ctypes import LittleEndianStructure, Union, c_ubyte, c_ushort, c_uint

CPU_SLEEP_QUANTUM = 0.05

class InterruptVector(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cs', c_ushort),
    ('ip', c_ushort)
  ]

#
# Service routines
# Very short routines with just one purpose - used in case there's no binary specified fo core
#

class ServiceRoutine(object):
  code = None

  def __init__(self):
    super(ServiceRoutine, self).__init__()

    self.translated = False

    self.page = None
    self.csb = None
    self.cs  = None
    self.dsb = None
    self.ds  = None

  def translate(self, memory):
    if self.translated:
      return

    import cpu.compile

    cs = UInt8(mm.SEGMENT_PROTECTED)
    ds = UInt8(cs.u8)
    self.page = memory.get_page(memory.alloc_page(segment = cs))
    self.csb = UInt16(self.page.base_address)
    self.dsb = UInt16(self.page.base_address + mm.PAGE_SIZE / 2)

    (csb, cs), (dsb, ds), symbols = cpu.compile.compile_buffer(self.code, csb = self.csb, dsb = self.dsb)

    self.cs = cs
    self.ds = ds
    self.translated = True

class HaltServiceRoutine(ServiceRoutine):
  code = [
    '  loada r0, 0',
    '  hlt r0'
  ]

class IdleLoopServiceRoutine(ServiceRoutine):
  code = [
    'main:',
    '  idle',
    '  jmp main'
  ]

class InterruptCounterRoutine(ServiceRoutine):
  code = [
    'data counter, "0"',
    'entry:',
    '  push r0',
    '  push r1',
    '  loada r0, &counter',
    '  load r1, r0',
    '  inc r1',
    '  store r0, r1',
    '  pop r1',
    '  pop r0',
    '  retint'

  ]

SERVICE_ROUTINES = {
  'halt': HaltServiceRoutine(),
  'idle_loop': IdleLoopServiceRoutine(),
  'interrupt_counter': InterruptCounterRoutine()
}

def log_cpu_core_state(core, logger = None):
  logger = logger or debug

  for reg in range(0, Registers.REGISTER_SPECIAL):
    logger(core.cpuid_prefix, 'reg%i=%s' % (reg, UINT16_FMT(core.REG(reg).u16)))

  logger(core.cpuid_prefix, 'cs=%s' % SEGM_FMT(core.CS().u16))
  logger(core.cpuid_prefix, 'ds=%s' % SEGM_FMT(core.DS().u16))
  logger(core.cpuid_prefix, 'ip=%s' % UINT16_FMT(core.IP().u16))
  logger(core.cpuid_prefix, 'sp=%s' % UINT16_FMT(core.SP().u16))
  logger(core.cpuid_prefix, 'priv=%i, hwint=%i' % (core.FLAGS().privileged, core.FLAGS().hwint))
  logger(core.cpuid_prefix, 'eq=%i, z=%i, o=%i' % (core.FLAGS().eq, core.FLAGS().z, core.FLAGS().o))
  logger(core.cpuid_prefix, 'thread=%s, keep_running=%s, idle=%s' % (core.thread.name, core.keep_running, core.idle))
  logger(core.cpuid_prefix, 'exit_code=%i' % core.exit_code)

  if core.current_instruction:
    ins, _ = instructions.disassemble_instruction(core.current_instruction, core.memory.read_u16(core.CS_ADDR(core.IP().u16), privileged = True))
    logger(core.cpuid_prefix, 'current=%s' % ins)
  else:
    logger(core.cpuid_prefix, 'current=')

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#%u:#%u: ' % (cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.registers = registers.RegisterSet()

    self.current_instruction = None

    self.keep_running = True
    self.thread = None
    self.idle = False

    self.exit_code = 0

  def die(self, exc):
    error(str(exc))
    log_cpu_core_state(self)
    self.keep_running = False

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

  def CS_ADDR(self, address):
    return segment_addr_to_addr(self.CS().u16 & 0xFF, address)

  def DS_ADDR(self, address):
    return segment_addr_to_addr(self.DS().u16 & 0xFF, address)

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
      sp = UInt24(self.DS_ADDR(self.SP().u16))

      debug(self.cpuid_prefix, '__push: save %s (%s) to %s' % (reg, UINT16_FMT(self.REG(reg).u16), ADDR_FMT(sp.u24)))

      self.MEM_OUT(sp.u24, self.REG(reg).u16)

  def __pop(self, *regs):
    for reg in regs:
      sp = UInt24(self.DS_ADDR(self.SP().u16))

      self.REG(reg).u16 = self.MEM_IN(sp.u24).u16

      debug(self.cpuid_prefix, '__pop: load %s (%s) from %s' % (reg, UINT16_FMT(self.REG(reg).u16), ADDR_FMT(sp.u24)))
      self.SP().u16 += 2

  def __do_interrupt(self, table_address, index):
    debug(self.cpuid_prefix, '__do_interrupt: table=%s, index=%i' % (ADDR_FMT(table_address.u24), index))

    self.__push(Registers.FLAGS, Registers.IP, Registers.DS, Registers.CS)

    self.privileged = 1

    self.CS().u16 = self.memory.read_u16(table_address.u24 + index * 4).u16
    self.IP().u16 = self.memory.read_u16(table_address.u24 + index * 4 + 2).u16

    debug(self.cpuid_prefix, '__do_interrupt: registers saved and new CS:IP loaded')

  def __do_int(self, index):
    self.do_interrupt(self.memory.read_u16(self.memory.header.int_table_address + index * 2))

  def __do_irq(self, index):
    debug(self.cpuid_prefix, '__do_irq: %s' % index)

    self.__do_interrupt(UInt24(self.memory.header.irq_table_address), index)
    self.FLAGS().hwint = 0
    self.idle = False

    debug(self.cpuid_prefix, '__do_irq: CPU state prepared to handle IRQ')

  def __do_retint(self):
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
    MEM_OUT8  = lambda addr, val: self.memory.write_u8(addr, val)
    MEM_OUT16 = lambda addr, val: self.memory.write_u16(addr, val)
    IP        = lambda: self.registers.ip
    FLAGS     = lambda: self.registers.flags.flags
    CS        = lambda: self.registers.cs
    DS        = lambda: self.registers.ds

    CS_ADDR = lambda addr: segment_addr_to_addr(self.CS().u16 & 0xFF, addr)
    DS_ADDR = lambda addr: segment_addr_to_addr(self.DS().u16 & 0xFF, addr)

    def IP_IN():
      addr = CS_ADDR(IP().u16)
      ret = MEM_IN16(addr)

      debug(self.cpuid_prefix, 'IP_IN: cs=%s, ip=%s, addr=%s, value=%s' % (SEGM_FMT(CS().u16), ADDR_FMT(IP().u16), ADDR_FMT(addr), UINT16_FMT(ret.u16)))

      IP().u16 += 2
      return ret

    saved_IP = IP().u16

    # Read next instruction
    debug(self.cpuid_prefix, '"Load new instruction" phase')

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
    info(self.cpuid_prefix, '%s: %s' % (UINT16_FMT(saved_IP), instructions.disassemble_instruction(self.current_instruction, disassemble_next_cell)[0]))
    log_cpu_core_state(self)

    debug(self.cpuid_prefix, '"Execute instruction" phase')

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

      self.halt()

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
      addr = DS_ADDR(REGI1().u16)

      if ins.byte:
        MEM_OUT8(addr, REGI2().u16 & 0xFF)
      else:
        MEM_OUT16(addr, REGI2().u16)

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

      elif REGI1().u16  > REGI2().u16:
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

    elif opcode == Opcodes.MOV:
      REGI1().u16 = REGI2().u16

    else:
      raise CPUException('Unknown opcode: %i' % opcode)

  def loop(self):
    info(self.cpuid_prefix, 'booted')
    log_cpu_core_state(self)

    while self.keep_running:
      irq_source = None
      irq_queue  = self.cpu.machine.queued_irqs

      if self.idle:
        debug(self.cpuid_prefix, 'idle => wait for irq to happen')
        irq_source = irq_queue.get(True)

      elif self.registers.flags.flags.hwint:
        debug(self.cpuid_prefix, 'running => check for irq in queue')

        try:
          irq_source = irq_queue.get(False)
        except Queue.Empty:
          pass

      if irq_source:
        debug(self.cpuid_prefix, ' IRQ encountered: %s' % irq_source.irq)

        try:
          self.__do_irq(irq_source.irq)
        except CPUException, e:
          self.die(e)
          break

        irq_queue.task_done()

      if not self.keep_running:
        break

      try:
        self.step()
      except CPUException, e:
        self.die(e)
        break

    info(self.cpuid_prefix, 'halted')
    log_cpu_core_state(self)

  def boot(self, init_state):
    cs, csb, ds, dsb, sp, privileged = init_state

    self.REG(Registers.CS).u16 = cs.u8
    self.REG(Registers.DS).u16 = ds.u8
    self.REG(Registers.IP).u16 = csb.u16
    self.REG(Registers.SP).u16 = sp.u16
    self.FLAGS().privileged = 1 if privileged else 0

    self.thread = threading.Thread(target = self.loop, name = 'Core #%i:#%i' % (self.cpu.id, self.id))
    self.thread.start()

  def halt(self):
    self.keep_running = False

    info(self.cpuid_prefix, 'asked to halt')
    log_cpu_core_state(self)

class CPU(object):
  def __init__(self, machine, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#%i:' % cpuid

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()
    self.cores = [CPUCore(i, self, self.memory) for i in range(0, cores)]

    self.keep_running = True
    self.thread = None

    self.exit_code = 0

  def loop(self):
    info(self.cpuid_prefix, 'booted')

    while self.keep_running:
      time.sleep(CPU_SLEEP_QUANTUM * 10)

      if len([core for core in self.cores if core.thread.is_alive()]) == 0:
        break

    info(self.cpuid_prefix, 'halted')

  def boot(self, init_states):
    for core in self.cores:
      core.boot(init_states.pop(0))

    self.thread = threading.Thread(target = self.loop, name = 'CPU #%i' % self.id)
    self.thread.start()

  def halt(self):
    for core in self.cores:
      core.halt()

    irq_queue = self.machine.queued_irqs

    for _ in self.cores:
      debug(self.cpuid_prefix, 'qsize: %i, maxsize: %i' % (irq_queue.qsize(), irq_queue.maxsize))
      irq_queue.put(None)

