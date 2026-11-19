"""Collect static assets without runtime secrets, database or S3 access."""
from .settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = 'build-only-static-collection-does-not-start-a-server'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
