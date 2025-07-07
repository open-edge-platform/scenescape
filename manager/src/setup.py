# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
