# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages

setup(
    name='scene_common',
    package_dir={'': '.'},
    packages=find_packages(where='.'),
    python_requires='>=3.7',
    license='Apache-2.0',
    version='1.0.0',
    author='Intel Corporation',
    description='SceneScape core functionality',
)
