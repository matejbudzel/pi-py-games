from setuptools import Extension, setup


setup(ext_modules=[Extension("common._fbcopy", ["src/common/_fbcopy.c"])])
