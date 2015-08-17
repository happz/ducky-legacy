from setuptools import setup

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
        'ducky.io_handlers',
        'ducky.irq',
        'ducky.mm'
      ],
      package_dir = {'ducky': 'ducky'},
      zip_safe = False,
      install_requires = [
        'enum34',
        'tabulate',
        'colorama',
        'pytty',
        'coverage',
        'lxml',
        'beautifulsoup4',
        'nose-timer'
      ],
     )
