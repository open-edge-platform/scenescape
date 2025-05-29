# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
