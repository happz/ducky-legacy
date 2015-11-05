import unittest
import os

from tests import get_tempfile
from ducky.tools import setup_logger
from ducky.mm import MalformedBinaryError
from ducky.mm.binary import File, SectionFlags

class Tests(unittest.TestCase):
  def test_bad_magic(self):
    tmp = get_tempfile()
    tmp.close()

    logger = setup_logger()

    with File.open(logger, tmp.name, 'w') as f_out:
      h_file = f_out.create_header()
      h_file.magic = File.MAGIC - 1
      f_out.save()

    try:
      with File.open(logger, tmp.name, 'r') as f_in:
        f_in.load()

    except MalformedBinaryError as e:
      assert e.args[0] == 'Magic cookie not recognized!'

    finally:
      os.unlink(tmp.name)

  def test_bad_section_type(self):
    tmp = get_tempfile()
    tmp.close()

    logger = setup_logger()

    with File.open(logger, tmp.name, 'w') as f_out:
      f_out.create_header()

      h_section = f_out.create_section()
      h_section.type = 254  # should be safe, not so many section types exist
      h_section.items = 0
      h_section.data_size = 0
      h_section.file_size = 0
      h_section.name = f_out.string_table.put_string('.foo')
      h_section.base = 0
      h_section.flags = SectionFlags.create()

      f_out.set_content(h_section, [])

      f_out.save()

    try:
      with File.open(logger, tmp.name, 'r') as f_in:
        f_in.load()

    except MalformedBinaryError as e:
      assert e.args[0] == 'Unknown section header type 254'

    finally:
      os.unlink(tmp.name)
