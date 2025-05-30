# Copyright (C) 2022-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from setuptools import setup, find_packages

import os

# Application Naming
APP_NAME = 'manager'
APP_PROPER_NAME = 'SceneScape'
APP_BASE_NAME = 'scenescape'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
  with open(BASE_DIR + '/' + APP_NAME + '/version.txt') as f:
    APP_VERSION_NUMBER = f.readline().rstrip()
    print(APP_PROPER_NAME + " version " + APP_VERSION_NUMBER)
except IOError:
  print(APP_PROPER_NAME + " version.txt file not found.")
  APP_VERSION_NUMBER = "Unknown"

setup(
    name='manager',
    packages=find_packages(),
    license='Intel Confidential',
    version=APP_VERSION_NUMBER,
    author='Intel Corporation',
    description='SceneScape core functionality',
    )
