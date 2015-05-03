from setuptools import setup

setup(name = 'ducky',
      version = '1.0',
      description = 'Simple virtual/CPU simulator',
      long_description = 'Ducky is a simple virtual CPU/machine simulator, with modular design and interesting features.',
      author = 'Milos Prchlik',
      author_email = 'happz@happz.cz',
      license = 'MIT',
      packages = ['ducky'],
      zip_safe = False,
      install_requires = [
        'threading2',
        'enum34',
        'colorama',
        'pytty',
        'coverage',
        'lxml',
        'beautifulsoup4'
      ],
     )
