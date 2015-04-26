import StringIO

from ConfigParser import ConfigParser, NoSectionError, NoOptionError

from util import str2int

def bool2option(b):
  return 'yes' if b else 'no'

class MachineConfig(ConfigParser):
  def __init__(self, *args, **kwargs):
    ConfigParser.__init__(self, *args, **kwargs)

    self.binaries_cnt    = 0
    self.breakpoints_cnt = 0
    self.mmaps_cnt       = 0
    self.storages_cnt    = 0

  def get(self, section, option, default = None):
    try:
      return ConfigParser.get(self, section, option)

    except (NoSectionError, NoOptionError):
      return default

  def set(self, section, option, value, *args, **kwargs):
    ConfigParser.set(self, section, option, str(value), *args, **kwargs)

  def getint(self, section, option, default = None):
    try:
      v = ConfigParser.get(self, section, option)
      return str2int(v) if v is not None else default

    except (NoSectionError, NoOptionError):
      return default

  _boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True, '0': False, 'no': False, 'false': False, 'off': False}

  def getbool(self, section, option, default = None):
    try:
      v = ConfigParser.get(self, section, option).lower()

      if v is None:
        return default

      if v not in self._boolean_states:
        raise ValueError('Not a boolean: %s' % v)

      return self._boolean_states[v]

    except (NoSectionError, NoOptionError):
      return default

  def getfloat(self, section, option, default = None):
    try:
      v = ConfigParser.get(self, section, option)
      return float(v) if v is not None else default

    except (NoSectionError, NoOptionError):
      return default

  def read(self, *args, **kwargs):
    ConfigParser.read(self, *args, **kwargs)

    self.__count_binaries()
    self.__count_breakpoints()
    self.__count_mmaps()

  def dumps(self):
    s = StringIO.StringIO()
    self.write(s)
    return s.getvalue()

  def __sections_with_prefix(self, prefix):
    return [s_name for s_name in self.sections() if s_name.startswith(prefix)]

  def __count(self, prefix):
    return len(self.__sections_with_prefix(prefix))

  def __count_binaries(self):
    self.binaries_cnt = self.__count('binary-')

  def __count_breakpoints(self):
    self.breakpoints_cnt = self.__count('breakpoint-')

  def __count_mmaps(self):
    self.mmaps_cnt = self.__count('mmap-')

  def __count_storages(self):
    self.storages_cnt = self.__count('storage-')

  def iter_binaries(self):
    for s_name in self.__sections_with_prefix('binary-'):
      yield s_name

  def iter_breakpoints(self):
    for s_name in self.__sections_with_prefix('breakpoint-'):
      yield s_name

  def iter_mmaps(self):
    for s_name in self.__sections_with_prefix('mmap-'):
      yield s_name

  def iter_storages(self):
    for s_name in self.__sections_with_prefix('storage-'):
      yield s_name

  def add_binary(self, filename, segment = None, core = None, entry = None):
    binary_section = 'binary-%s' % self.binaries_cnt
    self.binaries_cnt += 1

    self.add_section(binary_section)
    self.set(binary_section, 'file', filename)

    if segment:
      self.set(binary_section, 'segment', segment)

    if core:
      self.set(binary_section, 'core', core)

    if entry:
      self.set(binary_section, 'entry', entry)

  def add_breakpoint(self, core, address, active = None, flip = None, ephemeral = None, countdown = None):
    bp_section = 'breakpoint-%i' % self.breakpoints_cnt
    self.breakpoints_cnt += 1

    self.add_section(bp_section)
    self.set(bp_section, 'core', core)
    self.set(bp_section, 'address', address)

    if active is not None:
      self.set(bp_section, 'active', bool2option(active))

    if flip is not None:
      self.set(bp_section, 'flip', bool2option(flip))

    if ephemeral is not None:
      self.set(bp_section, 'ephemeral', bool2option(ephemeral))

    if countdown is not None:
      self.set(bp_section, 'countdown', str(countdown))

  def add_mmap(self, filepath, address, size, offset = None, access = None, shared = None):
    mmap_section = 'mmap-%i' % self.mmaps_cnt
    self.mmaps_cnt += 1

    self.add_section(mmap_section)
    self.set(mmap_section, 'file', filepath)
    self.set(mmap_section, 'address', address)
    self.set(mmap_section, 'size', size)

    if offset is not None:
      self.set(mmap_section, 'offset', offset)

    if access is not None:
      self.set(mmap_section, 'access', access)

    if shared is not None:
      self.set(mmap_section, 'shared', shared)

  def add_storage(self, driver, id, filepath = None):
    st_section = 'storage-%i' % self.storages_cnt
    self.storages_cnt += 1

    self.add_section(st_section)
    self.set(st_section, 'driver', driver)
    self.set(st_section, 'id', id)

    if filepath is not None:
      self.set(st_section, 'file', filepath)
