import enum
import Queue
import re
import threading

from util import debug

ADDRESS_ALL = (-1, -1)
ADDRESS_ANY = (-1,  0)

def thread_to_cid():
  cid = threading.current_thread().name.split(' ')[1].split(':')

  return (int(cid[0][1:]), int(cid[1][1:]))

class BaseMessage(object):
  def __init__(self, address, audience = None):
    super(BaseMessage, self).__init__()

    self.address = address
    self.bus = None

    self.audience = audience

    if audience:
      self.lock = threading.RLock()
      self.cond = threading.Condition(self.lock)
      self.delivered_to = 0

  def delivered(self):
    if not self.audience:
      return

    debug('msg.delivered: msg=%s, thread=%s' % (self.__class__.__name__, threading.current_thread().name))

    with self.lock:
      self.delivered_to += 1
      if self.delivered_to < self.audience:
        return

      self.cond.notifyAll()

  def wait(self):
    if not self.audience:
      return

    debug('msg.wait: msg=%s, thread=%s' % (self.__class__.__name__, threading.current_thread().name))

    with self.lock:
      self.cond.wait()

class HandleIRQ(BaseMessage):
  def __init__(self, address, irq_source, **kwargs):
    super(HandleIRQ, self).__init__(address, **kwargs)

    self.irq_source = irq_source

class HaltCore(BaseMessage):
  pass

class SuspendCore(BaseMessage):
  def __init__(self, *args, **kwargs):
    super(SuspendCore, self).__init__(*args, **kwargs)

    self.wake_up = threading.Event()
    self.wake_up.clear()

class MessageBus(object):
  def __init__(self):
    super(MessageBus, self).__init__()

    self.messages = {
      -1: {
        0: [] # ANY slot
      }
    }

    self.lock = threading.RLock()
    self.condition = threading.Condition(self.lock)

  def register(self):
    cpuid, coreid = thread_to_cid()

    debug('bus.register: core=#%i:#%i' % (cpuid, coreid))

    with self.lock:
      if cpuid not in self.messages:
        self.messages[cpuid] = {}

      if coreid not in self.messages[cpuid]:
        self.messages[cpuid][coreid] = []

  def get_msg_slot(self, msg):
    return self.messages[msg.address[0]][msg.address[1]]

  def get_core_slot(self):
    cpuid, coreid = thread_to_cid()
    return self.messages[cpuid][coreid]

  def get_any_slot(self):
    return self.messages[-1][0]

  def publish(self, msg, high_priority = False):
    debug('bus.publish: msg=%s, addr=%s' % (msg.__class__.__name__, msg.address))

    def __enqueue(slot):
      if high_priority:
        slot.insert(0, msg)
      else:
        slot.append(msg)

    with self.lock:
      if msg.address == ADDRESS_ALL:
        for cpuid, core_slots in self.messages.items():
          if cpuid == -1:
            continue

          for coreid, core_slot in core_slots.items():
            debug('bus.publish: %s queued for #%i:#%i' % (msg.__class__.__name__, cpuid, coreid))
            __enqueue(core_slot)

      else:
        __enqueue(self.get_msg_slot(msg))

      self.condition.notifyAll()

  def receive(self, sleep = True):
    debug('bus.receive: core=#%i:#%i' % thread_to_cid())

    while True:
      with self.lock:
        slot = self.get_any_slot()
        if len(slot) > 0:
          return slot.pop(0)

        slot = self.get_core_slot()
        if len(slot) > 0:
          return slot.pop(0)

        if not sleep:
          debug('bus.receive: empty queue, return')
          return None

        debug('bus.receive: empty queue, sleep')
        self.condition.wait()

