from util import debug

from threading2 import current_thread, RLock, Condition, Event

ADDRESS_LIST = (-1, -2)
ADDRESS_ALL  = (-1, -1)
ADDRESS_ANY  = (-1,  0)

def thread_to_cid():
  cid = current_thread().name.split(' ')[1].split(':')

  return (int(cid[0][1:]), int(cid[1][1:]))

def core_to_cid(core):
  return (core.cpu.id, core.id)

class BaseMessage(object):
  def __init__(self, address, audience = None):
    super(BaseMessage, self).__init__()

    self.address = address
    self.bus = None

    self.audience = audience

    if audience:
      self.lock = RLock()
      self.cond = Condition(self.lock)
      self.delivered_to = 0

  def delivered(self):
    if not self.audience:
      return

    debug('msg.delivered: msg=%s, thread=%s', self.__class__.__name__, current_thread().name)

    with self.lock:
      self.delivered_to += 1
      if self.delivered_to < len(self.audience):
        return

      self.cond.notifyAll()

  def wait(self):
    if not self.audience:
      return

    debug('msg.wait: msg=%s, thread=%s', self.__class__.__name__, current_thread().name)

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

    self.wake_up = Event()
    self.wake_up.clear()

class MessageBus(object):
  def __init__(self, machine):
    super(MessageBus, self).__init__()

    self.machine = machine

    self.queue_any = []

    self.lock = RLock()
    self.condition = Condition(self.lock)

  def register(self, __core):
    debug('bus.register: core=#%i:#%i', __core.cpu.id, __core.id)

    __core.machine_bus_queue = []

  def publish(self, msg, high_priority = False):
    debug('bus.publish: msg=%s, addr=%s', msg.__class__.__name__, msg.address)

    def __enqueue_for_core(__core):
      if high_priority:
        __core.machine_bus_queue.insert(0, msg)
      else:
        __core.machine_bus_queue.append(msg)

      debug('bus.publish: %s queued for #%i:#%i', msg.__class__.__name__, __core.cpu.id, __core.id)

    if msg.address == ADDRESS_ALL:
      self.machine.for_each_core(__enqueue_for_core)

    elif msg.address == ADDRESS_LIST:
      for __core in msg.audience:
        __enqueue_for_core(__core)

    elif msg.address == ADDRESS_ANY:
      if high_priority:
        self.queue_any.insert(0, msg)
      else:
        self.queue_any.append(msg)

    with self.lock:
      self.condition.notifyAll()

  def receive(self, core, sleep = True):
    debug('bus.receive: core=#%i:#%i' % core_to_cid(core))

    while True:
      try:
        return self.queue_any.pop(0)

      except IndexError:
        pass

      try:
        return core.machine_bus_queue.pop(0)

      except IndexError:
        pass

      if not sleep:
        debug('bus.receive: empty queue, return')
        return None

      debug('bus.receive: empty queue, sleep')
      with self.lock:
        self.condition.wait()
