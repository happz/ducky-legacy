from setuptools import setup, Extension

mod_native_data_cache = Extension('ducky.native.data_cache', sources = ['ducky/native/data_cache.c'])

setup(name = 'ducky',
      version = '1.0',
      description = 'Simple virtual/CPU simulator',
      long_description = 'Ducky is a simple virtual CPU/machine simulator, with modular design and interesting features.',
      author = 'Milos Prchlik',
      author_email = 'happz@happz.cz',
      license = 'MIT',
      packages = [
        'ducky',
        'ducky.cpu',
        'ducky.cpu.coprocessor',
        'ducky.mm',
        'ducky.devices',
        'ducky.native'
      ],
      package_dir = {'ducky': 'ducky'},
      zip_safe = False,
      install_requires = [
        'enum34',
        'tabulate',
        'colorama'
      ],
      ext_modules = [
        mod_native_data_cache
      ]
     )
