# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import re
import sys
import platform
import subprocess

from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext
from distutils.version import LooseVersion

class CMakeExtension(Extension):
  def __init__(self, name, sourcedir=''):
    Extension.__init__(self, name, sources=[])
    self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
  def run(self):
    try:
      out = subprocess.check_output(['cmake', '--version'])
    except OSError:
      raise RuntimeError("CMake must be installed to build the following extensions: " +
                         ", ".join(e.name for e in self.extensions))

    if platform.system() == "Windows":
      cmake_version = LooseVersion(re.search(r'version\s*([\d.]+)', out.decode()).group(1))
      if cmake_version < '3.1.0':
        raise RuntimeError("CMake >= 3.1.0 is required on Windows")

    for ext in self.extensions:
      self.build_extension(ext)

  def build_extension(self, ext):
    extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
    # required for auto-detection of auxiliary "native" libs
    if not extdir.endswith(os.path.sep):
      extdir += os.path.sep

    cmake_args = ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=' + extdir,
                  '-DPYTHON_EXECUTABLE=' + sys.executable,
                  '-DCMAKE_INSTALL_RPATH=$ORIGIN',
                  '-DCMAKE_BUILD_WITH_INSTALL_RPATH:BOOL=ON',
                  '-DCMAKE_INSTALL_RPATH_USE_LINK_PATH:BOOL=OFF',
                  '-DBUILD_TESTING:BOOL=OFF']

    cfg = 'Debug' if self.debug else 'Release'
    build_args = ['--config', cfg]

    if platform.system() == "Windows":
      cmake_args += ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), extdir)]
      if sys.maxsize > 2**32:
        cmake_args += ['-A', 'x64']
      build_args += ['--', '/m']
    else:
      cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]
      build_args += ['--', '-j4']

    env = os.environ.copy()
    env['CXXFLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXXFLAGS', ''),
                                                          self.distribution.get_version())
    if not os.path.exists(self.build_temp):
      os.makedirs(self.build_temp)
    subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
    subprocess.check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)

requirements = [
        'numpy>=1.17.1',
        'numpy-quaternion>=2019.12.11.22.25.52',
        'networkx',
        'scipy',
]

setup(
    name='robot_vision',
    description='Algorithms for robot vision, tracking and fusion',
    version='1.1.0',
    license='Intel Copyright',
    author='Intel Labs',
    author_email='',
    python_requires='>=3.7',
    install_requires=requirements,
    packages=find_packages('python/src'),
    package_dir={'':'python/src'},
    ext_modules=[CMakeExtension('robot_vision.extensions.')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
)
