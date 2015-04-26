import Queue

class ReactorTask(object):
  def runnable():
    return False

  def run():
    pass

class CallInReactorTask(ReactorTask):
  def __init__(self, fn, *args, **kwargs):
    self.fn = fn
    self.args = args
    self.kwargs = kwargs

  def runnable(self):
    return True

  def run(self):
    self.fn(*self.args, **self.kwargs)

class Reactor(object):
  _reactor = None

  def __init__(self):
    self.tasks = []
    self.events = Queue.Queue()

  @staticmethod
  def reactor():
    if Reactor._reactor is None:
      Reactor._reactor = Reactor()

    return Reactor._reactor

  def add_task(self, task):
    self.tasks.append(task)

  def remove_task(self, task):
    self.tasks.remove(task)

  def add_event(self, event):
    self.events.put(event)

  def add_call(self, fn, *args, **kwargs):
    self.add_event(CallInReactorTask(fn, *args, **kwargs))

  def run(self):
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
