"""
This module provides simple reactor core that runs each of registered tasks at
least once during one iteration of its internal loop.

Reactor is a singleton, there should be no need to create Reactor instance.

There are two different kinds of objects that reactor manages:

- task - it's called periodicaly, at least once in each reactor loop iteration
- event - asynchronous events are queued and executed before running any tasks.
  If there are no runnable tasks, reactor loop waits for incomming events.
"""

import Queue

class ReactorTask(object):
  """
  Base class for all reactor tasks.
  """

  def runnable():
    """
    Returns ``True`` if task can be run.
    """

    return False

  def run():
    """
    This method is called by reactor to perform task's actions.
    """

    pass

class CallInReactorTask(ReactorTask):
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

class Reactor(object):
  """
  Main reactor class. Never to be instantiated by application code, always
  import ``reactor`` from this module:

  >>> from reactor import reactor

  Or:

  >>> from reactor import Reactor
  >>> reactor = Reactor.reactor()
  """

  _reactor = None

  def __init__(self):
    self.tasks = []
    self.events = Queue.Queue()

  @staticmethod
  def reactor():
    """
    Return reactor. Reactor is a singleton, if there is an existing reactor
    object, it is returned, otherwise a new one is created.
    """

    if Reactor._reactor is None:
      Reactor._reactor = Reactor()

    return Reactor._reactor

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

  def run(self):
    """
    Starts reactor loop. Enters endless loop, calling runnable tasks and events,
    and - in case there are no runnable tasks - waits for new events.

    When there are no tasks managed by reactor, loop quits.
    """

    while True:
      if not self.tasks:
        break

      runnable_tasks = [task for task in self.tasks if task.runnable()]

      if runnable_tasks:
        for task in runnable_tasks:
          task.run()

        while not self.events.empty():
          e = self.events.get_nowait()
          e.run()

      else:
        e = self.events.get()
        e.run()

reactor = Reactor.reactor()
