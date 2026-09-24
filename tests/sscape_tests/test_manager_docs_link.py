# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from manager.settings import get_docs_version


TEMPLATE_PATH = (
  Path(__file__).resolve().parents[2] / 'manager' / 'backend' / 'manager' /
  'templates' / 'sscape' / 'base.html'
)


@pytest.mark.parametrize(
  'version, expected', [
    ('2026.3.0-dev', 'dev'),
    ('2026.2.0', '2026.2'),
    ('2026.2.0-rc1', 'dev'),
    ('2026.2.0-rc2', 'dev'),
    ('', 'dev'),
    ('Unknown', 'dev'),
    ('invalid-version', 'dev'),
  ],
)
def test_docs_version(version, expected):
  assert get_docs_version(version) == expected


def test_documentation_link_uses_dynamic_version():
  template = TEMPLATE_PATH.read_text()

  assert 'https://docs.openedgeplatform.intel.com/{{ DOCS_VERSION }}/scenescape/index.html' in template
  assert 'https://docs.openedgeplatform.intel.com/2026.2/scenescape/index.html' not in template
