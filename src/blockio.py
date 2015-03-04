import os

import profiler

from cpu.registers import Registers
from io_handlers import IOHandler
from irq import InterruptList
from irq.virtual import VirtualInterrupt, VIRTUAL_INTERRUPTS
from mm import UInt8, UInt16, UInt24, UInt32, segment_addr_to_addr
from util import debug, warn

from threading2 import Thread, Lock, Event

BLOCK_SIZE = 1024


class StorageAccessError(Exception):
  pass


class StorageIOHandler(IOHandler):
  def __init__(self, *args, **kwargs):
    super(StorageIOHandler, self).__init__(*args, **kwargs)

    self.lock = Lock()

    self.op_index = 0
    self.op = None

    self.finished_event = Event()
    self.finished_event.clear()

  def read_u16_512(self):
    debug('read_u16_512')

    with self.lock:
      if self.op:
        debug('SIO running, defer caller')
        return UInt16(0)

      debug('reserve SIO')
      self.op = []
      self.op_index += 1
      self.finished_event.clear()

      return UInt16(self.op_index)

  def read_u16_514(self):
    debug('read_u16_514')

    with self.lock:
      if not self.finished_event.is_set():
        debug('SIO still running')
        return UInt16(0)

      debug('SIO finished, reset')
      self.op = None
      return UInt16(self.op_index)

  def write_u16_514(self, value):
    self.op.append(value.u16)

    if len(self.op) != 7:
      return

    debug('start SIO: %s', str(self.op))

    device = self.machine.get_storage_by_id(str(self.op[1]))
    if not device:
      warn('SIO attempt to access unknown device %s', self.op[1])
      self.finished_event.set()
      return

    read = True if self.op[0] == 0 else False
    if read:
      src = UInt32(self.op[2] | (self.op[3] << 16))
      dst = UInt24(segment_addr_to_addr(self.op[5] & 0xFF, self.op[4]))
    else:
      src = UInt24(segment_addr_to_addr(self.op[3] & 0xFF, self.op[2]))
      dst = UInt32(self.op[4] | (self.op[5] << 16))

    cnt = UInt8(self.op[6])

    target = device.read_block if read else device.write_block

    debug('start SIO thread: target=%s, args=%s', target, str((src, dst, cnt, self.finished_event)))
    sio_thread = Thread(target = target, args = (src, dst, cnt, self.finished_event), priority = 0.0)
    sio_thread.start()

class Storage(object):
  def __init__(self, machine, sid, size):
    super(Storage, self).__init__()

    self.machine = machine
    self.id = sid
    self.size = size

    self.profiler = profiler.STORE.get_machine_profiler()

  def do_read_block(self, src, dst, cnt):
    pass

  def do_write_block(self, src, dst, cnt):
    pass

  def read_block(self, src, dst, cnt, event):
    self.profiler.enable()

    debug('read_block: id=%s, src=%s, dst=%s, cnt=%s', self.id, src, dst, cnt)

    if (src + cnt) * BLOCK_SIZE > self.size:
      self.profiler.disable()
      raise StorageAccessError('Out of bounds access: storage size %s is too small' % self.size)

    self.do_read_block(src, dst, cnt)

    if event:
      event.set()

    self.profiler.disable()

  def write_block(self, src, dst, cnt, event):
    self.profiler.enable()

    debug('write_block: id=%s, src=%s, dst=%s, cnt=%s', self.id, src, dst, cnt)

    if (dst + cnt) * BLOCK_SIZE > self.size:
      self.profiler.disable()
      raise StorageAccessError('Out of bounds access: storage size %s is too small' % self.size)

    self.do_write_block(src, dst, cnt)

    if event:
      event.set()

    self.profiler.disable()

class FileBackedStorage(Storage):
  def __init__(self, machine, sid, path):
    st = os.stat(path)

    super(FileBackedStorage, self).__init__(machine, sid, st.st_size)

    self.lock = Lock()
    self.path = path
    self.file = None

  def boot(self):
    self.file = open(self.path, 'r+b')

  def halt(self):
    debug('BIO: halt')

    self.file.flush()
    self.file.close()

  def do_read_block(self, src, dst, cnt):
    debug('do_read_block: src=%s, dst=%s, cnt=%s', src, dst, cnt)

    with self.lock:
      self.file.seek(src * BLOCK_SIZE)
      buff = self.file.read(cnt * BLOCK_SIZE)

    for c in buff:
      self.machine.memory.write_u8(dst, ord(c))
      dst += 1

    debug('BIO: %s bytes read from %s:%s', cnt * BLOCK_SIZE, self.file.name, dst * BLOCK_SIZE)

  def do_write_block(self, src, dst, cnt):
    buff = []

    for _ in range(0, cnt * BLOCK_SIZE):
      buff.append(chr(self.machine.memory.read_u8(src)))
      src += 1

    buff = ''.join(buff)

    with self.lock:
      self.file.seek(dst * BLOCK_SIZE)
      self.file.write(buff)

    debug('BIO: %s bytes written at %s:%s', cnt * BLOCK_SIZE, self.file.name, dst * BLOCK_SIZE)

STORAGES = {
  'block': FileBackedStorage,
}

class BlockIOInterrupt(VirtualInterrupt):
  def run(self, core):
    core.DEBUG('BIO requested')

    r0 = core.REG(Registers.R00)

    device = self.machine.get_storage_by_id(r0.value)
    if not device:
      core.WARN('BIO: unknown device: id=%s', r0.value)
      r0.value = 0xFFFF
      return

    r1 = core.REG(Registers.R01)
    r2 = core.REG(Registers.R02)
    r3 = core.REG(Registers.R03)
    r4 = core.REG(Registers.R04)
    DS = core.REG(Registers.DS)

    if r1.value == 0:
      handler = device.read_block
      src = r2.value
      dst = segment_addr_to_addr(DS.value & 0xFF, r3.value)

    elif r1.value == 1:
      handler = device.write_block
      src = segment_addr_to_addr(DS.value & 0xFF, r2.value)
      dst = r3.value

    else:
      core.WARN('BIO: unknown operation: op=%s', r1.value)
      r0.value = 0xFFFF
      return

    cnt = r4.value & 0x00FF

    try:
      handler(src, dst, cnt, None)
      r0.value = 0

    except StorageAccessError, e:
      core.ERROR('BIO: operation failed')
      core.EXCEPTION(e)

      r0.value = 0xFFFF

VIRTUAL_INTERRUPTS[InterruptList.BLOCKIO.value] = BlockIOInterrupt
