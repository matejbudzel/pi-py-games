from setuptools import Extension, setup


# This is strictly a Raspberry Pi framebuffer accelerator.  Desktop Pygame
# games and fbdev's established Python copy fallback must install without a C
# compiler or Python development headers.
setup(ext_modules=[Extension("common._fbcopy", ["src/common/_fbcopy.c"], optional=True)])
