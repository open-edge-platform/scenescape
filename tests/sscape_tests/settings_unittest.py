# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from manager.settings import *

AXES_ENABLED = True
DATABASES = None

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:'
    }
}

# Configure templates for unit tests
_repo_root = Path(__file__).resolve().parents[2]
_templates_dir = _repo_root / "manager" / "src" / "templates"

if _templates_dir.is_dir():
  TEMPLATES = [
    {
      'BACKEND': 'django.template.backends.django.DjangoTemplates',
      'DIRS': [str(_templates_dir)],
      'APP_DIRS': True,
      'OPTIONS': {
        'context_processors': [
          'django.template.context_processors.debug',
          'django.template.context_processors.request',
          'django.contrib.auth.context_processors.auth',
          'django.contrib.messages.context_processors.messages',
        ],
      },
    },
  ]

