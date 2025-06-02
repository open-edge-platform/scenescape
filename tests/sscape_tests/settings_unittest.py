from manager.settings import *

AXES_ENABLED = True
DATABASES = None

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test_db.sqlite3'
    }
}
