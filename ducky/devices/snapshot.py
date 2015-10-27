from . import Device

class SnapshotStorage(Device):
  def __init__(self, machine, name, *args, **kwargs):
    super(SnapshotStorage, self).__init__(machine, 'snapshot', name, *args, **kwargs)

  @staticmethod
  def create_from_config(machine, config, section):
    return SnapshotStorage(machine, section)

  def save_snapshot(self, snapshot):
    pass

  def halt(self):
    self.machine.capture_state()


class FileSnapshotStorage(SnapshotStorage):
  def __init__(self, machine, name, filepath = None, *args, **kwargs):
    super(FileSnapshotStorage, self).__init__(machine, name, *args, **kwargs)

    self.filepath = filepath

  @staticmethod
  def create_from_config(machine, config, section):
    return FileSnapshotStorage(machine, section, filepath = config.get(section, 'filepath', None))

  def save_snapshot(self, snapshot):
    snapshot.save(self.filepath)
    self.machine.INFO('snapshot: saved in file %s', self.filepath)

  def boot(self):
    self.machine.INFO('snapshot: storage ready, backed by file %s', self.filepath)

  def halt(self):
    super(FileSnapshotStorage, self).halt()

    self.save_snapshot(self.machine.last_state)

class DefaultFileSnapshotStorage(FileSnapshotStorage):
  @staticmethod
  def create_from_config(machine, config, section):
    return DefaultFileSnapshotStorage(machine, section, filepath = 'ducky-snapshot.bin')
