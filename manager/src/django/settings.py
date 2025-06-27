# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from datetime import timedelta
from manager.secrets import *

# Application Naming
APP_NAME = 'manager'
APP_PROPER_NAME = 'Intel® SceneScape'
APP_BASE_NAME = 'scenescape'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['*']
DEFAULT_CHARSET = "utf-8"

# Application definition

INSTALLED_APPS = [
  'django.contrib.admin',
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'django.contrib.messages',
  'django.contrib.staticfiles',
  'rest_framework',
  'rest_framework.authtoken',
  'axes',
  APP_NAME,
]

REST_FRAMEWORK = {
  'DEFAULT_AUTHENTICATION_CLASSES': [
    'rest_framework.authentication.TokenAuthentication',
  ],
  'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
  'PAGE_SIZE': 100
}

MIDDLEWARE = [
  'django.middleware.security.SecurityMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django_session_timeout.middleware.SessionTimeoutMiddleware',
  'django.middleware.common.CommonMiddleware',
  'django.middleware.csrf.CsrfViewMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
  'django.contrib.messages.middleware.MessageMiddleware',
  'django.middleware.clickjacking.XFrameOptionsMiddleware',
  'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = APP_NAME + '.urls'

TEMPLATES = [
  {
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
      'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        APP_NAME + '.context_processors.selected_settings'
      ],
    },
  },
]

WSGI_APPLICATION = APP_NAME + '.wsgi.application'

LOGOUT_EXPIRES = 10*60*60 # 10 hours cookie timeout
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = LOGOUT_EXPIRES
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_SECONDS = LOGOUT_EXPIRES
SESSION_EXPIRE_AFTER_LAST_ACTIVITY = True # Reset expire timer after user activity

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = timedelta(seconds=30)
AXES_LOCKOUT_URL = '/account_locked'
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.postgresql_psycopg2',
    'ATOMIC_REQUESTS': True,
    'NAME': APP_BASE_NAME,
    'USER': APP_BASE_NAME,
    'PASSWORD': DATABASE_PASSWORD,
    'HOST': 'localhost',
    'PORT': '',
  }
}

# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
  {
    'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
  },
]

AUTHENTICATION_BACKENDS = [
  'axes.backends.AxesBackend',
  'django.contrib.auth.backends.ModelBackend',
]

# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'
USE_TZ = True
USE_L10N = True
TIME_ZONE = 'UTC'
USE_I18N = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATIC_URL = '/static/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

DOCS_ROOT = os.path.join(BASE_DIR, 'manager', 'docs')
DOCS_URL = '/docs/'

MODEL_ROOT = os.path.join(BASE_DIR, 'models')
MODEL_URL = '/models/'

LOGIN_URL = 'sign_in'

# Get the running host
KUBERNETES_SERVICE_HOST = 'KUBERNETES_SERVICE_HOST' in os.environ

# Get the version number
try:
  with open(BASE_DIR + '/' + APP_NAME + '/version.txt') as f:
    APP_VERSION_NUMBER = f.readline().rstrip()
    print(APP_PROPER_NAME + " version " + APP_VERSION_NUMBER)
except IOError:
  print(APP_PROPER_NAME + " version.txt file not found.")
  APP_VERSION_NUMBER = "Unknown"

# Set up support for proxy headers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if DEBUG:
  INSTALLED_APPS += ( 'debug_toolbar',)
  MIDDLEWARE += (
    'manager.middleware.Custom500Middleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
  )
  DEBUG_TOOLBAR_PANELS = [
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.request.RequestPanel',
    'debug_toolbar.panels.sql.SQLPanel',
    'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'debug_toolbar.panels.cache.CachePanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
  ]

  def true(request):
    return False #True

  DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': "%s.true" % __name__,
  }

  DEBUG_PROPAGATE_EXCEPTIONS = True

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
BROWSER_AUTH_FILE = "/run/secrets/browser.auth"
ROOT_CERT_FILE = "/run/secrets/certs/scenescape-ca.pem"

from manager.settings_local import *
