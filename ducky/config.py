"""
VM configuration management
"""

import functools

from six import iteritems
from six.moves import StringIO
from six.moves.configparser import ConfigParser, NoSectionError, NoOptionError

from .util import str2int

def bool2option(b):
  """
  Get config-file-usable string representation of boolean value.

  :param bool b: value to convert.
  :rtype: string
  :returns: ``yes`` if input is ``True``, ``no`` otherwise.
  """

  return 'yes' if b else 'no'

class MachineConfig(ConfigParser):
  """
  Contains configuration of the whole VM, and provides methods for parsing,
  inspection and extending this configuration.
  """

  def __init__(self, *args, **kwargs):
    ConfigParser.__init__(self, *args, **kwargs)

    self.binaries_cnt    = 0
    self.breakpoints_cnt = 0
    self.mmaps_cnt       = 0
    self.devices_cnt     = 0

  def get(self, section, option, default = None):
    """
    Get value for an option.

    :param string section: config section.
    :param string option: option name,
    :param default: this value will be returned, if no such option exists.
    :rtype: string
    :returns: value of config option.
    """

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
        raise ValueError('Not a boolean: {}'.format(v))

      return self._boolean_states[v]

    except (NoSectionError, NoOptionError):
      return default

  def getfloat(self, section, option, default = None):
    try:
      v = ConfigParser.get(self, section, option)
      return float(v) if v is not None else default

    except (NoSectionError, NoOptionError):
      return default

  def create_getters(self, section):
    return (functools.partial(self.get, section), functools.partial(self.getbool, section), functools.partial(self.getint, section))

  def read(self, *args, **kwargs):
    ConfigParser.read(self, *args, **kwargs)

    self.__count_binaries()
    self.__count_breakpoints()
    self.__count_mmaps()
    self.__count_devices()

  def dumps(self):
    s = StringIO()
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

  def __count_devices(self):
    self.devices_cnt = self.__count('device-')

  def iter_binaries(self):
    for s_name in self.__sections_with_prefix('binary-'):
      yield s_name

  def iter_breakpoints(self):
    for s_name in self.__sections_with_prefix('breakpoint-'):
      yield s_name

  def iter_mmaps(self):
    for s_name in self.__sections_with_prefix('mmap-'):
      yield s_name

  def iter_devices(self):
    for s_name in self.__sections_with_prefix('device-'):
      yield s_name

  def iter_storages(self):
    for s_name in self.__sections_with_prefix('device-'):
      if self.get(s_name, 'klass') != 'storage':
        continue

      yield s_name

  def add_binary(self, filename, segment = None, core = None, entry = None):
    """
    Add another binary to configuration.

    :param string filename: path to binary (``file`` option).
    :param int segment: if set, assign specific segment to this binary's (``segment`` option).
    :param string core: if set, assign specific core to this binary (``core`` option).
    :param string entry: if set, set binary's entry point (``entry`` option).
    """

    binary_section = 'binary-{}'.format(self.binaries_cnt)
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
    bp_section = 'breakpoint-{}'.format(self.breakpoints_cnt)
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
    mmap_section = 'mmap-{}'.format(self.mmaps_cnt)
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

  def add_device(self, klass, driver, **kwargs):
    """
    Add another device to the configuration.

    :param string klass: class of the device (``klass`` option).
    :param string driver: device driver - dot-separated path to class (``driver``
      option).
    :param kwargs: all keyword arguments will be added to the section as device
      options.
    """

    section = 'device-{}'.format(self.devices_cnt)
    self.devices_cnt += 1

    self.add_section(section)
    self.set(section, 'klass', klass)
    self.set(section, 'driver', driver)

    for name, value in iteritems(kwargs):
      self.set(section, name, value)

    return section

  def add_storage(self, driver, sid, filepath = None):
    """
    Add another storage to the configuration.

    :param string driver: storage's driver - dot-separated path to class (``driver`` option).
    :param int sid: storage's SID (``sid`` options).
    :param string filepath: path to backend file, if there's any (``filepath`` option).
    """

    self.add_device('storage', driver, sid = sid, filepath = filepath)
