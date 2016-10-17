import os

from ducky.mm import MalformedBinaryError
from ducky.mm.binary import File, SectionFlags

from .. import get_tempfile, LOGGER

def test_bad_magic_save():
  tmp = get_tempfile()
  tmp.close()

  with File.open(LOGGER, tmp.name, 'w') as f_out:
    f_out.header.magic = File.MAGIC - 1

    try:
      f_out.save()

    except MalformedBinaryError as e:
      assert e.args[0] == '%s: magic cookie not recognized!' % f_out.name

    finally:
      os.unlink(tmp.name)

def test_bad_section_type_save():
  tmp = get_tempfile()
  tmp.close()

  with File.open(LOGGER, tmp.name, 'w') as f_out:
    section = f_out.create_section(name = '.foo')

    section.header.type = 254  # should be safe, not so many section types exist
    section.header.data_size = 0
    section.header.file_size = 0
    section.header.base = 0
    section.header.flags = SectionFlags.create().to_encoding()

    section.payload = []

    try:
      f_out.save()

    except MalformedBinaryError as e:
      assert e.args[0] == 'Unknown section header type 254'

    finally:
      os.unlink(tmp.name)
