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

setup(
    name='controller',
    package_dir={'': '.'},
    packages=find_packages(),
    python_requires='>=3.7',
    license='Intel Confidential',
    version='1.0.0',
    author='Intel Corporation',
    description='SceneScape core functionality',
)
