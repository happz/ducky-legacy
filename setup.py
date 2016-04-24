from setuptools import setup, Extension
from setuptools.command.test import test as TestCommand
import sys

mod_native_data_cache = Extension('ducky.native.data_cache', sources = ['ducky/native/data_cache.c'])

install_requires = [
  'colorama',
  'enum34',
  'tabulate',
  'pycparser',
  'six',
  'mako',
  'Twisted',
  'autobahn'
]

tests_requires = [
  'tox',
  'virtualenv'
]

class Tox(TestCommand):
  user_options = [('tox-args=', 'a', 'Arguments to pass to tox')]

  def initialize_options(self):
    TestCommand.initialize_options(self)
    self.tox_args = None

  def finalize_options(self):
    TestCommand.finalize_options(self)
    self.test_args = []
    self.test_suite = True

  def run_tests(self):
    import tox
    import shlex

    args = self.tox_args
    if args:
      args = shlex.split(self.tox_args)

    errno = tox.cmdline(args=args)
    sys.exit(errno)

setup(name = 'ducky',
      version = '3.0',
      description = 'Simple virtual CPU/machine simulator',
      long_description = 'Ducky is a simple virtual CPU/machine simulator, with modular design and interesting features.',
      url = 'https://github.com/happz/ducky',
      download_url = 'https://github.com/happz/ducky/tarball/3.0',
      author = 'Milos Prchlik',
      author_email = 'happz@happz.cz',
      license = 'MIT',
      classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Other Audience',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Programming Language :: Forth',
        'Programming Language :: Assembly',
        'Topic :: Software Development :: Assemblers',
        'Topic :: Software Development :: Code Generators',
        'Topic :: Software Development :: Compilers',
        'Topic :: Software Development :: Interpreters'
      ],
      keywords = 'virtual CPU simulator',
      packages = [
        'ducky',
        'ducky.cc',
        'ducky.cc.passes',
        'ducky.cpu',
        'ducky.cpu.coprocessor',
        'ducky.mm',
        'ducky.devices',
        'ducky.tools'
      ],
      entry_points = {
        'console_scripts': [
          'ducky-as = ducky.tools.as:main',
          'ducky-cc = ducky.tools.cc:main',
          'ducky-ld = ducky.tools.ld:main',
          'ducky-vm = ducky.tools.vm:main',
          'ducky-objdump = ducky.tools.objdump:main',
          'ducky-coredump = ducky.tools.coredump:main',
          'ducky-profile = ducky.tools.profile:main',
          'ducky-img = ducky.tools.img:main',
          'ducky-defs = ducky.tools.defs:main'
        ]
      },
      package_dir = {'ducky': 'ducky'},
      zip_safe = False,
      install_requires = install_requires,
      tests_require = tests_requires,
      cmdclass = {
        'test': Tox
      }
     )
