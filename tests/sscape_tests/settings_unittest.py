# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from manager.settings import *

AXES_ENABLED = True
DATABASES = None

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test_db.sqlite3'
    }
}
