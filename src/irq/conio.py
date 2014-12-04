import irq

class Console(irq.IRQSource):
  def __init__(self, conio, *args, **kwargs):
    super(Console, self).__init__(*args, **kwargs)

    self.conio = conio

  def on_tick(self):
    return self.conio.check_available_input()
