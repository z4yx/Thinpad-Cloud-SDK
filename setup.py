#!/usr/bin/env python3

from distutils.core import setup
import os

about = {}
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'thinpad', '__version__.py'), 'r') as f:
    exec(f.read(), about)

setup(name='thinpad-cloud',
      version=about['__version__'],
      description=about['__description__'],
      author=about['__author__'],
      license=about['__license__'],
      packages = ['thinpad'],
      install_requires=['socketIO-client-2~=0.7.5', 'requests~=2.19'],
    )
