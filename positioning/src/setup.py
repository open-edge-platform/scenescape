# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from setuptools import setup, find_packages

setup(
    name='positioning',
    package_dir={'': '.'},
    packages=find_packages(where='.'),
    python_requires='>=3.9',
    install_requires=[
        'protobuf>=5.29.0,<7',
        'grpcio>=1.71.2',
        'numpy',
        'scipy',
    ],
    license='Apache-2.0',
    version='1.0.0',
    author='Intel Corporation',
    description='Scenescape Positioning Service library (PTZ pose math and contracts)',
)
