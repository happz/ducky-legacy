"""
This module provides simple reactor core that runs each of registered tasks at
least once during one iteration of its internal loop.

There are two different kinds of objects that reactor manages:

- task - it's called periodicaly, at least once in each reactor loop iteration
- event - asynchronous events are queued and executed before running any tasks.
  If there are no runnable tasks, reactor loop waits for incomming events.
"""

import Queue
import select

from .interfaces import IReactorTask

class CallInReactorTask(IReactorTask):
  """
  This task request running particular function during the reactor loop. Useful
  for planning future work, and for running tasks in reactor's thread.
  """

  def __init__(self, fn, *args, **kwargs):
    self.fn = fn
    self.args = args
    self.kwargs = kwargs

  def runnable(self):
    return True

  def run(self):
    self.fn(*self.args, **self.kwargs)

class RunInIntervalTask(IReactorTask):
  def __init__(self, ticks, fn, *args, **kwargs):
    self.ticks = ticks
    self.counter = 0

    self.fn = fn
    self.args = args
    self.kwargs = kwargs

  def runnable(self):
    return True

  def run(self):
    self.counter += 1

    if self.counter < self.ticks:
      return

    self.counter = 0

    self.fn(self, *self.args, **self.kwargs)

class SelectTask(IReactorTask):
  def __init__(self, machine, fds, *args, **kwargs):
    super(SelectTask, self).__init__(*args, **kwargs)

    self.machine = machine
    self.fds = fds

  def runnable(self):
    return True

  def run(self):
    fds = [fd for fd in self.fds.iterkeys()]
    self.machine.DEBUG('SelectTask: fds=%s', fds)

    f_read, f_write, f_err = select.select(fds, fds, fds, 0)

    self.machine.DEBUG('  select: f_read=%s, f_write=%s, f_err=%s', f_read, f_write, f_err)

    for fd in f_err:
      if not self.fds[fd][2]:
        continue

      self.machine.DEBUG('  trigger err: fd=%s, handler=%s', fd, self.fds[fd][2])
      self.fds[fd][2]()

    for fd in f_read:
      if fd in f_err:
        continue

      if fd not in self.fds or not self.fds[fd][0]:
        continue

      self.machine.DEBUG('  trigger read: fd=%s, handler=%s', fd, self.fds[fd][0])
      self.fds[fd][0]()

    for fd in f_write:
      if fd in f_err:
        continue

      if fd not in self.fds or not self.fds[fd][1]:
        continue

      self.machine.DEBUG('  trigger err: fd=%s, handler=%s', fd, self.fds[fd][1])
      self.fds[fd][1]()

class Reactor(object):
  """
  Main reactor class.
  """

  def __init__(self, machine):
    self.machine = machine

    self.tasks = []
    self.events = Queue.Queue()

    self.fds = {}
    self.fds_task = None

  def add_task(self, task):
    """
    Register task with reactor's main loop.
    """

    self.tasks.append(task)

  def remove_task(self, task):
    """
    Unregister task, it will never be run again.
    """

    self.tasks.remove(task)

  def add_event(self, event):
    """
    Enqueue asynchronous event.
    """

    self.events.put(event)

  def add_call(self, fn, *args, **kwargs):
    """
    Enqueue function call. Function will be called in reactor loop.
    """

    self.add_event(CallInReactorTask(fn, *args, **kwargs))

  def add_fd(self, fd, on_read = None, on_write = None, on_error = None):
    self.machine.DEBUG('Reactor.add_fd: fd=%s, on_read=%s, on_write=%s, on_error=%s', fd, on_read, on_write, on_error)

    assert fd not in self.fds

    self.fds[fd] = (on_read, on_write, on_error)

    if len(self.fds) == 1:
      self.fds_task = SelectTask(self.machine, self.fds)
      self.add_task(self.fds_task)

  def remove_fd(self, fd):
    self.machine.DEBUG('Reactor.remove_fd: fd=%s', fd)

    assert fd in self.fds

    del self.fds[fd]

    if not self.fds:
      self.remove_task(self.fds_task)
      self.fds_task = None

  def run(self):
    """
    Starts reactor loop. Enters endless loop, calling runnable tasks and events,
    and - in case there are no runnable tasks - waits for new events.

    When there are no tasks managed by reactor, loop quits.
    """

    while True:
      if not self.tasks:
        break

      ran_tasks = 0

      for task in self.tasks:
        if task.runnable() is not True:
          continue

        task.run()
        ran_tasks += 1

      if ran_tasks > 0:
        while not self.events.empty():
          e = self.events.get_nowait()
          e.run()

      else:
        e = self.events.get()
        e.run()
