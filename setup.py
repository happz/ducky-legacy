from setuptools import setup, Extension

mod_native_data_cache = Extension('ducky.native.data_cache', sources = ['ducky/native/data_cache.c'])

setup(name = 'ducky',
      version = '1.0',
      description = 'Simple virtual/CPU simulator',
      long_description = 'Ducky is a simple virtual CPU/machine simulator, with modular design and interesting features.',
      url = 'https://github.com/happz/ducky',
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
        'Programming Language :: Python :: 2 :: Only',
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
        'ducky.native',
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
          'ducky-profile = ducky.tools.profile:main'
        ]
      },
      package_dir = {'ducky': 'ducky'},
      zip_safe = False,
      install_requires = [
        'enum34',
        'tabulate',
        'colorama',
        'pycparser',
      ],
      ext_modules = [
        mod_native_data_cache
      ]
     )
