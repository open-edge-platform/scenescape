# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from setuptools import find_packages, setup

setup(
  name='scene_metadata',
  package_dir={'': '.'},
  packages=find_packages(where='.', include=['scene_metadata', 'scene_metadata.*']),
  python_requires='>=3.11',
  license='Apache-2.0',
  version='0.1.0',
  author='Intel Corporation',
  description='Scenescape Scene Metadata — Timescale event log and MCP query plane',
)
