from setuptools import setup, Extension
from Cython.Build import cythonize

ext = Extension("monorail.ai", ["monorail/ai.pyx"])
setup(packages=[], ext_modules=cythonize([ext], language_level=3))
