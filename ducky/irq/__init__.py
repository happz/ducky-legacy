"""
IRQs, and interrupts at general, are a way how external resource providers can
interrupt execution flow, and deliver resources, previously requested by
running program, or inform running programs about important external events.

Ducky VM knows 3 types of interrupts:
 - irq, aka. "hardware" interrupt - simulates hardware resource: clock, console,
   block, serial or character device, etc.
 - int, aka. "software" interrupt - invoked by running progam itself using
   ``INT`` instruction.
 - virtual interrupts - subset of software interrupts but their routines are
   implemented by ducky VM itself, to provide access to a complex internal
   resources
"""

import enum

from .. import machine

class IRQList(enum.IntEnum):
  """
  List of known IRQ sources.
  """

  TIMER = 0
  CONIO = 1

  IRQ_COUNT = 64

class InterruptList(enum.IntEnum):
  """
  List of known software interrupts.
  """

  HALT    = 0
  BLOCKIO = 1
  VMDEBUG = 2
  CONIO   = 3
  MM      = 4
  MATH    = 5

  INT_COUNT = 64

class IRQSource(machine.MachineWorker):
  """
  IRQ source. Represents an hardware resource, e.g. clock or block device,
  that can interrupt running programs.

  :param ducky.machine.Machine machine: machine this IRQ source is attached to.
  """

  def __init__(self, machine):
    super(IRQSource, self).__init__()

    self.machine = machine

    self.irq = None
    self.is_maskable = True

  def boot(self):
    pass

class IRQSourceSet(object):
  """
  Set of IRQ sources, which can be seen as a interrupt controller.
  """

  def __init__(self):
    super(IRQSourceSet, self).__init__()

    self.__sources = [None for _ in range(0, IRQList.IRQ_COUNT)]

  def __check_irq_limits(self, irq):
    if irq < 0 or irq >= IRQList.IRQ_COUNT:
      raise IndexError('IRQ out of range: irq={}'.format(irq))

  def __getitem__(self, irq):
    self.__check_irq_limits(irq)
    return self.__sources[irq]

  def __setitem__(self, irq, source):
    self.__check_irq_limits(irq)
    self.__sources[irq] = source

  def __delitem__(self, irq):
    self.__check_irq_limits(irq)
    self.__sources[irq] = None

  def __iter__(self):
    return iter(self.__sources)

  def ihandlers(self):
    return self.__sources.itervalues()

  def __len__(self):
    return len(self.__sources)

  def __contains__(self, irq):
    self.__check_irq_limits(irq)
    return self.__sources is not None
