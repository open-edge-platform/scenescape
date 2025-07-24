# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from .secrets import *
from .settings import APP_BASE_NAME

DEBUG = True
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.postgresql_psycopg2',
    'NAME': APP_BASE_NAME,
    'USER': APP_BASE_NAME,
    'PASSWORD': DATABASE_PASSWORD,
    'HOST': 'pgserver',
    'PORT': '',
  }
}

SESSION_COOKIE_AGE = 60000 # 1000 minutes timeout
SECURE_CONTENT_TYPE_NOSNIFF = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_SECURITY_INSECURE = True
AXES_ENABLED = False
