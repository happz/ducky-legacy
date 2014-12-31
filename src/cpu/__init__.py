import Queue
import sys
import threading
import time

import assemble
import debugging
import instructions
import registers
import mm
import irq
import machine.bus

from mm import UInt8, UInt16, UInt24
from mm import SEGM_FMT, ADDR_FMT, UINT8_FMT, UINT16_FMT
from mm import segment_addr_to_addr

from registers import Registers, REGISTER_NAMES
from instructions import Opcodes
from core import CPUCoreState
from errors import CPUException, AccessViolationError, InvalidResourceError
from util import debug, info, warn, error

from ctypes import LittleEndianStructure, Union, c_ubyte, c_ushort, c_uint

CPU_SLEEP_QUANTUM = 0.05

class InterruptVector(LittleEndianStructure):
  _pack_ = 0
  _fields_ = [
    ('cs', c_ubyte),
    ('ds', c_ubyte),
    ('ip', c_ushort)
  ]

def log_cpu_core_state(core, logger = None):
  logger = logger or debug

  for i in range(0, Registers.REGISTER_SPECIAL, 4):
    regs = [(i + j) for j in range(0, 4) if (i + j) < Registers.REGISTER_SPECIAL]
    s = ['reg%02i=%s' % (reg, UINT16_FMT(core.REG(reg).u16)) for reg in regs]
    logger(core.cpuid_prefix, ' '.join(s))

  logger(core.cpuid_prefix, 'cs=%s      ds=%s' % (SEGM_FMT(core.CS().u16), SEGM_FMT(core.DS().u16)))
  logger(core.cpuid_prefix, 'fp=%s    sp=%s    ip=%s' % (UINT16_FMT(core.FP().u16), UINT16_FMT(core.SP().u16), UINT16_FMT(core.IP().u16)))
  logger(core.cpuid_prefix, 'priv=%i, hwint=%i, e=%i, z=%i, o=%i' % (core.FLAGS().privileged, core.FLAGS().hwint, core.FLAGS().e, core.FLAGS().z, core.FLAGS().o))
  logger(core.cpuid_prefix, 'thread=%s, keep_running=%s, idle=%s, exit=%i' % (core.thread.name, core.keep_running, core.idle, core.exit_code))

  if core.current_instruction:
    inst = instructions.disassemble_instruction(core.current_instruction)
    logger(core.cpuid_prefix, 'current=%s' % inst)
  else:
    logger(core.cpuid_prefix, 'current=')

class CPUCore(object):
  def __init__(self, coreid, cpu, memory_controller):
    super(CPUCore, self).__init__()

    self.cpuid_prefix = '#%u:#%u: ' % (cpu.id, coreid)

    self.id = coreid
    self.cpu = cpu
    self.memory = memory_controller

    self.message_bus = self.cpu.machine.message_bus
    self.suspend_events = []
    self.current_suspend_event = None

    self.registers = registers.RegisterSet()

    self.current_instruction = None

    self.keep_running = True
    self.thread = None
    self.idle = False

    self.exit_code = 0

    self.frames = []

    self.debug = debugging.DebuggingSet(self)

  def __repr__(self):
    return '#%i:#%i' % (self.cpu.id, self.id)

  def save_state(self, state):
    debug('core.save_state')

    core_state = CPUCoreState()

    core_state.cpuid = self.cpu.id
    core_state.coreid = self.id

    for reg in REGISTER_NAMES:
      if reg == 'flags':
        core_state.flags.u16 = self.registers.flags.u16

      else:
        setattr(core_state, reg, self.registers[reg].u16)

    core_state.exit_code = self.exit_code
    core_state.idle = 1 if self.idle else 0
    core_state.keep_running = 1 if self.keep_running else 0

    state.core_states.append(core_state)

  def load_state(self, core_state):
    for reg in REGISTER_NAMES:
      if reg == 'flags':
        self.registers.flags.u16 = core_state.flags.u16

      else:
        self.registers[reg].u16 = getattr(core_state, reg)

    self.exit_code = core_state.exit_code
    self.idle = True if core_state.idle else False
    self.keep_running = True if core_state.keep_running else False

  def die(self, exc):
    error(str(exc))
    log_cpu_core_state(self)
    self.keep_running = False

    if self.current_suspend_event:
      self.current_suspend_event.set()

  def FLAGS(self):
    return self.registers.flags.flags

  def REG(self, reg):
    return self.registers[reg]

  def MEM_IN(self, addr):
    return self.memory.read_u16(addr)

  def MEM_IN32(self, addr):
    return self.memory.read_u32(addr)

  def MEM_OUT(self, addr, value):
    self.memory.write_u16(addr, value)

  def IP(self):
    return self.registers.ip

  def SP(self):
    return self.registers.sp

  def FP(self):
    return self.registers.fp

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
    self.FLAGS().e = 0
    self.FLAGS().z = 0
    self.FLAGS().o = 0
    self.FLAGS().s = 0

    self.IP().u16 = new_ip

  def __symbol_for_ip(self):
    symbol, offset = self.cpu.machine.get_symbol_by_addr(UInt8(self.CS().u16), self.IP().u16)

    if not symbol:
      warn('JUMP: Unknown jump target: %s' % ADDR_FMT(self.IP().u16))
      return

    debug('JUMP: %s%s (%s)' % (symbol, ' + %s' % UINT16_FMT(offset.u16) if offset.u16 != 0 else '', ADDR_FMT(self.IP().u16)))

  def __raw_push(self, val):
    self.SP().u16 -= 2
    sp = UInt24(self.DS_ADDR(self.SP().u16))
    self.MEM_OUT(sp.u24, val.u16)

  def __raw_pop(self):
    sp = UInt24(self.DS_ADDR(self.SP().u16))
    ret = self.MEM_IN(sp.u24).u16
    self.SP().u16 += 2
    return UInt16(ret)

  def __push(self, *regs):
    for reg in regs:
      debug(self.cpuid_prefix, '__push: %s (%s) at %s' % (reg, UINT16_FMT(self.REG(reg).u16), UINT16_FMT(self.SP().u16 - 2)))
      self.__raw_push(self.REG(reg))

  def __pop(self, *regs):
    for reg in regs:
      self.REG(reg).u16 = self.__raw_pop().u16
      debug(self.cpuid_prefix, '__pop: %s (%s) from %s' % (reg, UINT16_FMT(self.REG(reg).u16), UINT16_FMT(self.SP().u16 - 2)))

  def __create_frame(self):
    self.__push(Registers.IP, Registers.FP)

    self.FP().u16 = self.SP().u16

    self.frames.append(self.SP().u16)

  def __destroy_frame(self):
    if self.frames[-1] != self.SP().u16:
      raise CPUException('Leaving frame with wrong SP: last saved SP: %s, current SP: %s' % (ADDR_FMT(self.frames[-1]), ADDR_FMT(self.SP().u16)))

    self.__pop(Registers.FP, Registers.IP)

    self.frames.pop()

    self.__symbol_for_ip()

  def __enter_interrupt(self, table_address, index):
    debug(self.cpuid_prefix, '__enter_interrupt: table=%s, index=%i' % (ADDR_FMT(table_address.u24), index))

    iv = self.memory.load_interrupt_vector(table_address, index)

    stack_page = self.memory.get_page(self.memory.alloc_page(UInt8(iv.ds)))
    stack_page.read = True
    stack_page.write = True

    old_SP = UInt16(self.SP().u16)
    old_DS = UInt16(self.DS().u16)

    self.DS().u16 = iv.ds
    self.SP().u16 = UInt16(stack_page.segment_address + mm.PAGE_SIZE).u16

    debug('push old DS')
    self.__raw_push(old_DS)
    debug('push old SP')
    self.__raw_push(old_SP)
    self.__push(Registers.CS, Registers.FLAGS)
    self.__push(*[i for i in range(0, Registers.REGISTER_SPECIAL)])
    self.__create_frame()

    self.privileged = 1

    self.CS().u16 = iv.cs
    self.IP().u16 = iv.ip

  def __exit_interrupt(self):
    debug(self.cpuid_prefix, '__exit_interrupt')

    self.__destroy_frame()
    self.__pop(*[i for i in reversed(range(0, Registers.REGISTER_SPECIAL))])
    self.__pop(Registers.FLAGS, Registers.CS)

    stack_page = self.memory.get_page(mm.addr_to_page(self.DS_ADDR(self.SP().u16)))

    old_SP = self.__raw_pop()
    old_DS = self.__raw_pop()

    self.DS().u16 = old_DS.u16
    self.SP().u16 = old_SP.u16

    self.memory.free_page(stack_page)

  def __do_int(self, index):
    debug(self.cpuid_prefix, '__do_int: %s' % index)

    self.__enter_interrupt(UInt24(self.memory.int_table_address), index)

    debug(self.cpuid_prefix, '__do_int: CPU state prepared to handle interrupt')

  def __do_irq(self, index):
    debug(self.cpuid_prefix, '__do_irq: %s' % index)

    self.__enter_interrupt(UInt24(self.memory.irq_table_address), index)
    self.FLAGS().hwint = 0
    self.idle = False

    debug(self.cpuid_prefix, '__do_irq: CPU state prepared to handle IRQ')
    log_cpu_core_state(self)

  # Do it this way to avoid pylint' confusion
  def __get_privileged(self):
    return self.FLAGS().privileged

  def __set_privileged(self, value):
    self.FLAGS().privileged = value

  privileged = property(__get_privileged, __set_privileged)

  def step(self):
    # pylint: disable-msg=R0912,R0914,R0915
    # "Too many branches"
    # "Too many local variables"
    # "Too many statements"

    REG       = lambda reg: self.registers[reg]
    MEM_IN8   = lambda addr: self.memory.read_u8(addr)
    MEM_IN16  = lambda addr: self.memory.read_u16(addr)
    MEM_IN32  = lambda addr: self.memory.read_u32(addr)
    MEM_OUT8  = lambda addr, val: self.memory.write_u8(addr, val)
    MEM_OUT16 = lambda addr, val: self.memory.write_u16(addr, val)
    IP        = lambda: self.registers.ip
    FLAGS     = lambda: self.registers.flags.flags
    CS        = lambda: self.registers.cs
    DS        = lambda: self.registers.ds

    CS_ADDR = lambda addr: segment_addr_to_addr(CS().u16 & 0xFF, addr)
    DS_ADDR = lambda addr: segment_addr_to_addr(DS().u16 & 0xFF, addr)

    def IP_IN():
      addr = CS_ADDR(IP().u16)
      ret = MEM_IN32(addr)

      debug(self.cpuid_prefix, 'IP_IN: cs=%s, ip=%s, addr=%s, value=%s' % (SEGM_FMT(CS().u16), ADDR_FMT(IP().u16), ADDR_FMT(addr), UINT16_FMT(ret.u32)))

      IP().u16 += 4
      return ret

    saved_IP = IP().u16

    # Read next instruction
    debug(self.cpuid_prefix, '"FETCH" phase')

    self.current_instruction = inst = instructions.decode_instruction(IP_IN())
    opcode = self.current_instruction.opcode

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

    def RI_VAL(inst):
      return REG(inst.ireg).u16 if inst.is_reg == 1 else inst.immediate

    def JUMP(inst):
      if inst.is_reg == 1:
        IP().u16 = REG(inst.ireg).u16
      else:
        IP().u16 += inst.immediate

      self.__symbol_for_ip()

    def CMP(x, y):
      FLAGS().e = 0
      FLAGS().ge = 0
      FLAGS().le = 0
      FLAGS().s = 0
      FLAGS().z = 0

      if   x == y:
        FLAGS().e = 1

        if x == 0:
          FLAGS().z = 1

      elif x  < y:
        FLAGS().s = 1

      elif x > y:
        FLAGS().s = 0

    def OFFSET_ADDR(inst):
      debug('offset addr: ireg=%s, imm=%s' % (inst.ireg, inst.immediate))
      addr = REG(inst.ireg).u16
      if inst.immediate != 0:
        addr += inst.immediate

      debug('offset addr: addr=%s' % addr)
      return DS_ADDR(addr)

    class AFLAGS_CTX(object):
      def __init__(self, reg):
        super(AFLAGS_CTX, self).__init__()

        self.reg = reg

      def __enter__(self):
        FLAGS().z = 0
        FLAGS().o = 0
        FLAGS().s = 0

      def __exit__(self, *args, **kwargs):
        debug('actx_exit: reg=%s' % UINT16_FMT(self.reg.u16))

        if self.reg.u16 == 0:
          FLAGS().z = 1
        #if self.dst.u16 overflow:
        #  FLAGS().o = 1

        return False

    debug(self.cpuid_prefix, '"EXECUTE" phase: %s %s' % (UINT16_FMT(saved_IP), instructions.disassemble_instruction(self.current_instruction)))
    log_cpu_core_state(self)

    if   opcode == Opcodes.NOP:
      pass

    elif opcode == Opcodes.LW:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 = MEM_IN16(OFFSET_ADDR(inst)).u16

    elif opcode == Opcodes.LB:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 = MEM_IN8(OFFSET_ADDR(inst)).u8

    elif opcode == Opcodes.LBU:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 = MEM_IN16(OFFSET_ADDR(inst)).u16

    elif opcode == Opcodes.LI:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 = inst.immediate

    elif opcode == Opcodes.STW:
      MEM_OUT16(OFFSET_ADDR(inst), REG(inst.reg).u16)

    elif opcode == Opcodes.STB:
      MEM_OUT8(OFFSET_ADDR(inst), REG(inst.reg).u16 & 0xFF)

    elif opcode == Opcodes.STBU:
      MEM_OUT8(OFFSET_ADDR(inst), (REG(inst.reg).u16 & 0xFF00) >> 8)

    elif opcode == Opcodes.MOV:
      REG(inst.reg1).u16 = REG(inst.reg2).u16

    elif opcode == Opcodes.SWP:
      v = UInt16(REG(inst.reg1).u16)
      REG(inst.reg1).u16 = REG(inst.reg2).u16
      REG(inst.reg2).u16 = v.u16

    elif opcode == Opcodes.CAS:
      FLAGS().e = 0

      v = self.memory.cas_16(DS_ADDR(REG(inst.r_addr)), REG(inst.r_test), REG(inst.r_rep))
      if v == True:
        FLAGS().e = 1
      else:
        REG(inst.r_test).u16 = v.u16

    elif opcode == Opcodes.INT:
      self.__do_int(RI_VAL(inst))

    elif opcode == Opcodes.RETINT:
      __check_protected_ins()

      self.__exit_interrupt()

    elif opcode == Opcodes.CALL:
      self.__create_frame()

      JUMP(inst)

    elif opcode == Opcodes.RET:
      self.__destroy_frame()

    elif opcode == Opcodes.CLI:
      __check_protected_ins()

      FLAGS().hwint = 0

    elif opcode == Opcodes.STI:
      __check_protected_ins()

      FLAGS().hwint = 1

    elif opcode == Opcodes.HLT:
      __check_protected_ins()

      self.exit_code = RI_VAL(inst)

      self.keep_running = False

    elif opcode == Opcodes.RST:
      __check_protected_ins()

      self.reset()

    elif opcode == Opcodes.IDLE:
      self.idle = True

    elif opcode == Opcodes.PUSH:
      self.__raw_push(UInt16(RI_VAL(inst)))

    elif opcode == Opcodes.POP:
      __check_protected_reg(inst.reg)

      self.__pop(inst.reg)

    elif opcode == Opcodes.INC:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 += 1

    elif opcode == Opcodes.DEC:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 -= 1

    elif opcode == Opcodes.ADD:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 += RI_VAL(inst)

    elif opcode == Opcodes.SUB:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 -= RI_VAL(inst)

    elif opcode == Opcodes.AND:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 &= RI_VAL(inst)

    elif opcode == Opcodes.OR:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 |= RI_VAL(inst)

    elif opcode == Opcodes.XOR:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 ^= RI_VAL(inst)

    elif opcode == Opcodes.NOT:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 = ~REG(inst.reg).u16

    elif opcode == Opcodes.SHIFTL:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 <<= RI_VAL(inst)

    elif opcode == Opcodes.SHIFTR:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 >>= RI_VAL(inst)

    elif opcode == Opcodes.IN:
      port = UInt16(RI_VAL(inst))

      __check_protected_port(port)
      __check_protected_reg(inst.reg)

      REG(inst.reg).u16 = self.cpu.machine.ports[port.u16].read_u16(port).u16

    elif opcode == Opcodes.INB:
      port = UInt16(RI_VAL(inst))

      __check_protected_port(port)
      __check_protected_reg(inst.reg)

      REG(inst.reg).u16 = UInt16(self.cpu.machine.ports[port.u16].read_u8(port).u8).u16

    elif opcode == Opcodes.OUT:
      port = UInt16(RI_VAL(inst))

      __check_protected_port(port)

      self.cpu.machine.ports[port.u16].write_u16(port, REG(inst.reg))

    elif opcode == Opcodes.OUTB:
      port = UInt16(RI_VAL(inst))

      __check_protected_port(port)

      self.cpu.machine.ports[port.u16].write_u8(port, UInt8(REG(inst.reg).u16 & 0xFF))

    elif opcode == Opcodes.CMP:
      CMP(REG(inst.reg).u16, RI_VAL(inst))

    elif opcode == Opcodes.J:
      JUMP(inst)

    elif opcode == Opcodes.BE:
      if FLAGS().e == 1:
        JUMP(inst)

    elif opcode == Opcodes.BNE:
      if FLAGS().e == 0:
        JUMP(inst)

    elif opcode == Opcodes.BZ:
      if FLAGS().z == 1:
        JUMP(inst)

    elif opcode == Opcodes.BNZ:
      if FLAGS().z == 0:
        JUMP(inst)

    elif opcode == Opcodes.BS:
      if FLAGS().s == 1:
        JUMP(inst)

    elif opcode == Opcodes.BNS:
      if FLAGS().s == 0:
        JUMP(inst)

    elif opcode == Opcodes.BG:
      if FLAGS().s == 0 and FLAGS().e == 0:
        JUMP(inst)

    elif opcode == Opcodes.BE:
      if FLAGS().s == 1 and FLAGS().e == 0:
        JUMP(inst)

    elif opcode == Opcodes.BGE:
      if FLAGS().s == 0 or FLAGS().e == 1:
        JUMP(inst)

    elif opcode == Opcodes.BLE:
      if FLAGS().s == 1 or FLAGS().e == 1:
        JUMP(inst)

    elif opcode == Opcodes.MUL:
      __check_protected_reg(inst.reg)

      with AFLAGS_CTX(REG(inst.reg)):
        REG(inst.reg).u16 *= RI_VAL(inst)

    else:
      raise CPUException('Unknown opcode: %i' % opcode)

    debug(self.cpuid_prefix, '"SYNC" phase:')
    log_cpu_core_state(self)

  def wake_up(self):
    debug(self.cpuid_prefix, 'wake_up')

    if self.current_suspend_event:
      self.current_suspend_event.set()
      self.current_suspend_event = None

  def suspend_on(self, event):
    debug(self.cpuid_prefix, 'asked to suspend')
    event.wait()
    debug(self.cpuid_prefix, 'unsuspended')

  def plan_suspend(self, event):
    debug(self.cpuid_prefix, 'plan suspend')
    self.suspend_events.append(event)
    debug(self.cpuid_prefix, 'suspend planned, wait for it')

  def check_for_events(self):
    debug(self.cpuid_prefix, 'check_for_events')

    msg = None

    if self.idle:
      debug(self.cpuid_prefix, 'idle => wait for new messages')
      msg = self.message_bus.receive(self)

    elif self.registers.flags.flags.hwint == 1:
      debug(self.cpuid_prefix, 'running => check for new message')
      msg = self.message_bus.receive(self, sleep = False)

    debug(self.cpuid_prefix, 'msg=%s' % msg)

    if msg:
      if isinstance(msg, machine.bus.HandleIRQ):
        debug(self.cpuid_prefix, 'IRQ encountered: %s' % msg.irq_source.irq)

        msg.delivered()

        try:
          self.__do_irq(msg.irq_source.irq)

        except CPUException, e:
          self.die(e)
          return False

      elif isinstance(msg, machine.bus.HaltCore):
        self.keep_running = False

        info(self.cpuid_prefix, 'asked to halt')
        log_cpu_core_state(self)

        msg.delivered()

        return False

      elif isinstance(msg, machine.bus.SuspendCore):
        msg.delivered()
        self.plan_suspend(msg.wake_up)

    self.debug.check()

    if self.suspend_events:
      self.current_suspend_event = self.suspend_events.pop(0)
      self.suspend_on(self.current_suspend_event)
      self.current_suspend_event = None

      debug(self.cpuid_prefix, 'woken up from suspend state, let check bus for new messages')

      return self.check_for_events()

    return True

  def loop(self):
    self.message_bus.register()

    info(self.cpuid_prefix, 'booted')
    log_cpu_core_state(self)

    while self.keep_running:
      if not self.check_for_events():
        break

      if not self.keep_running:
        break

      try:
        self.step()

      except CPUException, e:
        self.die(e)
        break

    info(self.cpuid_prefix, 'halted')
    log_cpu_core_state(self)

  def run(self):
    self.thread = threading.Thread(target = self.loop, name = 'Core #%i:#%i' % (self.cpu.id, self.id))
    self.thread.start()

  def boot(self, init_state):
    self.reset()

    cs, ds, sp, ip, privileged = init_state

    self.REG(Registers.CS).u16 = cs.u8
    self.REG(Registers.DS).u16 = ds.u8
    self.REG(Registers.IP).u16 = ip.u16
    self.REG(Registers.SP).u16 = sp.u16
    self.FLAGS().privileged = 1 if privileged else 0

class CPU(object):
  def __init__(self, machine, cpuid, cores = 1, memory_controller = None):
    super(CPU, self).__init__()

    self.cpuid_prefix = '#%i:' % cpuid

    self.machine = machine
    self.id = cpuid

    self.memory = memory_controller or mm.MemoryController()
    self.cores = [CPUCore(i, self, self.memory) for i in range(0, cores)]

    self.thread = None

  def living_cores(self):
    return [core for core in self.cores if core.thread and core.thread.is_alive()]

  def loop(self):
    info(self.cpuid_prefix, 'booted')

    while True:
      time.sleep(CPU_SLEEP_QUANTUM * 10)

      if len(self.living_cores()) == 0:
        break

    info(self.cpuid_prefix, 'halted')

  def run(self):
    for core in self.cores:
      core.run()

    self.thread = threading.Thread(target = self.loop, name = 'CPU #%i' % self.id)
    self.thread.start()

  def boot(self, init_states):
    for core in self.cores:
      if init_states:
        core.boot(init_states.pop(0))

import console

def cmd_set_core(console, cmd):
  """
  Set core address of default core used by control commands
  """

  console.default_core = console.machine.core(cmd[1])

def cmd_cont(console, cmd):
  """
  Continue execution until next breakpoint is reached
  """

  if console.default_core.current_suspend_event:
    console.default_core.current_suspend_event.set()

def cmd_step(console, cmd):
  """
  Step one instruction forward
  """

  core = console.default_core

  try:
    core.step()
    core.check_for_events()

    log_cpu_core_state(console.default_core, logger = console.info)

  except CPUException, e:
    core.die(e)

def cmd_next(console, cmd):
  """
  Proceed to the next instruction in the same stack frame.
  """

  core = console.default_core

  def __ip_addr(offset = 0):
    return core.CS_ADDR(core.IP().u16 + offset)

  try:
    inst = instructions.decode_instruction(core.MEM_IN32(__ip_addr()))

    if inst.opcode == Opcodes.CALL:
      from debugging import add_breakpoint

      add_breakpoint(core, core.IP().u16 + 4, ephemeral = True)

      if core.current_suspend_event:
        core.current_suspend_event.set()

    else:
      core.step()
      core.check_for_events()

      log_cpu_core_state(console.default_core, logger = console.info)

  except CPUException, e:
    core.die(e)

def cmd_core_state(console, cmd):
  """
  Print core state
  """

  log_cpu_core_state(console.default_core, logger = console.info)

console.Console.register_command('set_core', cmd_set_core)
console.Console.register_command('cont', cmd_cont)
console.Console.register_command('step', cmd_step)
console.Console.register_command('next', cmd_next)
console.Console.register_command('core_state', cmd_core_state)
